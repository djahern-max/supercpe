"""Enrollment: the record everything hangs off (ROADMAP structural
difference 2).

An enrollment pins the package versions it was created on and is served
those versions until it completes or expires; a course edit mid-enrollment
(which already requires unpublish -> re-review -> republish) never reaches
an in-flight participant. `status` is derived from `expires_at` and the
completion row, never stored. Rule violations raise
`EnrollmentRuleViolation` for the router to wrap in a 422
`{"errors": [...]}`, the same shape as everywhere else.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.assessment import RETAKES_ALLOWED
from app.constants.enrollment import ENROLLMENT_DAYS
from app.models.account import Account
from app.models.attempt import Attempt
from app.models.course import Course
from app.models.enrollment import Enrollment, LessonProgress, ReviewAnswer
from app.models.lesson_package import LessonPackage
from app.models.question import Question
from app.services import questions as questions_service


class EnrollmentRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def status(enrollment: Enrollment) -> str:
    """Derived, never stored: completed if a completion row exists, else
    voided if an admin ended access (018), else expired if past
    `expires_at`, else active. Voided is checked before expired so a
    voided enrollment stays voided when its year later runs out."""
    if enrollment.completion is not None:
        return "completed"
    if enrollment.voided_at is not None:
        return "voided"
    if _now() > enrollment.expires_at:
        return "expired"
    return "active"


def enroll(
    db: Session,
    account: Account,
    course: Course,
    created_by: Account | None,
    source: str = "admin",
) -> Enrollment:
    errors = []
    if course.status != "published":
        errors.append(
            f"course {course.course_code} is {course.status}; only published "
            "courses can be enrolled in"
        )
    if account.role != "participant":
        errors.append(
            f"{account.email} is a {account.role}; only participants can be "
            "enrolled"
        )
    if not account.is_active:
        errors.append(f"account {account.email} is deactivated")
    existing = next(
        (
            e
            for e in db.scalars(
                select(Enrollment).where(
                    Enrollment.account_id == account.id,
                    Enrollment.course_id == course.id,
                )
            )
            if status(e) == "active"
        ),
        None,
    )
    if existing is not None:
        errors.append(
            f"{account.email} already holds active enrollment {existing.id} "
            f"on {course.course_code}, expiring "
            f"{existing.expires_at.date().isoformat()}"
        )
    if errors:
        raise EnrollmentRuleViolation(errors)

    enrolled_at = _now()
    enrollment = Enrollment(
        account_id=account.id,
        course_id=course.id,
        enrolled_at=enrolled_at,
        # 9.02.2(3): "no longer than one year from the date of purchase or
        # enrollment" — a fact about the enrollment, stored at creation.
        expires_at=enrolled_at + timedelta(days=ENROLLMENT_DAYS),
        source=source,
        created_by_account_id=created_by.id if created_by else None,
        package_versions={
            str(cl.package_id): cl.package.version
            for cl in sorted(course.lessons, key=lambda cl: cl.position)
        },
    )
    db.add(enrollment)
    db.commit()
    return enrollment


def void(db: Session, enrollment: Enrollment, admin: Account) -> Enrollment:
    """The guarded admin action behind a refund whose policy answer is
    "access ends" (018). Deactivate-never-delete: stamps `voided_at` and
    who did it; the row, its progress, and its answers stay. Only an
    active enrollment can be voided — a completion is an immutable 9.02
    record no refund can unmake, and voiding an expired or already-voided
    enrollment has nothing left to end."""
    current = status(enrollment)
    if current != "active":
        raise EnrollmentRuleViolation(
            [
                f"enrollment {enrollment.id} is {current}, not active; "
                + (
                    "the completion and certificate are immutable 9.02 "
                    "records — a refund cannot unmake them"
                    if current == "completed"
                    else "there is no access left to end"
                )
            ]
        )
    enrollment.voided_at = _now()
    enrollment.voided_by_account_id = admin.id
    db.commit()
    return enrollment


def list_for_account(db: Session, account: Account) -> list[Enrollment]:
    return list(
        db.scalars(
            select(Enrollment)
            .where(Enrollment.account_id == account.id)
            .order_by(Enrollment.enrolled_at.desc(), Enrollment.id.desc())
        )
    )


def list_for_course(db: Session, course: Course) -> list[Enrollment]:
    return list(
        db.scalars(
            select(Enrollment)
            .where(Enrollment.course_id == course.id)
            .order_by(Enrollment.enrolled_at.desc(), Enrollment.id.desc())
        )
    )


def count_for_course(db: Session, course: Course) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.course_id == course.id)
    )


def packages_for(db: Session, enrollment: Enrollment) -> list[LessonPackage]:
    """The pinned package rows, in lesson order — what the player and
    assessment serve instead of the course's current lessons. Ordered by
    the course's current position for the same lesson (JSONB does not keep
    key order), falling back to the manifest position for a lesson that was
    detached after enrolling."""
    ids = [int(package_id) for package_id in enrollment.package_versions]
    rows = list(
        db.scalars(select(LessonPackage).where(LessonPackage.id.in_(ids)))
    )
    position_of = {
        cl.package.lesson_id: cl.position for cl in enrollment.course.lessons
    }
    rows.sort(
        key=lambda p: (
            position_of.get(p.lesson_id, p.manifest_position or 0),
            p.lesson_id,
        )
    )
    return rows


def pinned_package(
    db: Session, enrollment: Enrollment, package_id: int
) -> LessonPackage | None:
    """The pinned package row, or None when this package id is not part of
    the enrollment's pin (including newer versions of its own lessons)."""
    if str(package_id) not in enrollment.package_versions:
        return None
    return db.get(LessonPackage, package_id)


def review_questions_for(
    db: Session, enrollment: Enrollment
) -> list[tuple[LessonPackage, list[Question]]]:
    """The pinned review questions, grouped by lesson in order."""
    return [
        (
            package,
            [
                q
                for q in questions_service.for_package(db, package.id)
                if q.kind == "review"
            ],
        )
        for package in packages_for(db, enrollment)
    ]


def answers_by_question(db: Session, enrollment: Enrollment) -> dict[int, ReviewAnswer]:
    return {
        row.question_id: row
        for row in db.scalars(
            select(ReviewAnswer).where(
                ReviewAnswer.enrollment_id == enrollment.id
            )
        )
    }


def record_review_answer(
    db: Session, enrollment: Enrollment, question: Question, choice
) -> ReviewAnswer:
    """Upsert the 5.01.2 engagement record: a re-answer updates the row and
    `answered_at`. `is_correct` snapshots the verdict."""
    existing = db.scalar(
        select(ReviewAnswer).where(
            ReviewAnswer.enrollment_id == enrollment.id,
            ReviewAnswer.question_id == question.id,
        )
    )
    now = _now()
    if existing is None:
        existing = ReviewAnswer(
            enrollment_id=enrollment.id,
            question_id=question.id,
            choice_id=choice.id,
            is_correct=choice.is_correct,
            answered_at=now,
        )
        db.add(existing)
    else:
        existing.choice_id = choice.id
        existing.is_correct = choice.is_correct
        existing.answered_at = now
    db.commit()
    return existing


def record_progress(
    db: Session, enrollment: Enrollment, package: LessonPackage, furthest_seconds: int
) -> LessonProgress:
    """Monotonic: the furthest point watched is never lowered."""
    row = db.scalar(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.package_id == package.id,
        )
    )
    if row is None:
        row = LessonProgress(
            enrollment_id=enrollment.id,
            package_id=package.id,
            furthest_seconds=max(furthest_seconds, 0),
            updated_at=_now(),
        )
        db.add(row)
    elif furthest_seconds > row.furthest_seconds:
        row.furthest_seconds = furthest_seconds
        row.updated_at = _now()
    db.commit()
    return row


def failed_attempts(db: Session, enrollment: Enrollment) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(
            Attempt.enrollment_id == enrollment.id,
            Attempt.status == "failed",
        )
    )


def retakes_remaining(db: Session, enrollment: Enrollment) -> int:
    """Sittings left: the first sitting plus RETAKES_ALLOWED re-takes, less
    every failed (submitted or abandoned) attempt on this enrollment."""
    return max(1 + RETAKES_ALLOWED - failed_attempts(db, enrollment), 0)


def progress(db: Session, enrollment: Enrollment) -> dict:
    """Per pinned lesson: furthest seconds and review questions
    answered/total. `assessment_available` is true iff every pinned review
    question has an answer and the enrollment is active; `unanswered` names
    the missing questions by lesson for refusal messages."""
    progress_rows = {
        row.package_id: row
        for row in db.scalars(
            select(LessonProgress).where(
                LessonProgress.enrollment_id == enrollment.id
            )
        )
    }
    answered = answers_by_question(db, enrollment)

    lessons = []
    unanswered = []
    for position, (package, questions) in enumerate(
        review_questions_for(db, enrollment), start=1
    ):
        missing = [q.question_key for q in questions if q.id not in answered]
        if missing:
            unanswered.append(
                {"lesson_id": package.lesson_id, "question_keys": missing}
            )
        row = progress_rows.get(package.id)
        lessons.append(
            {
                "package_id": package.id,
                "lesson_id": package.lesson_id,
                "kind": package.kind,
                "version": package.version,
                "position": position,
                "title": package.title,
                "duration_seconds": package.duration_seconds,
                "furthest_seconds": row.furthest_seconds if row else 0,
                "review_answered": len(questions) - len(missing),
                "review_total": len(questions),
            }
        )

    return {
        "lessons": lessons,
        "review_answered": sum(l["review_answered"] for l in lessons),
        "review_total": sum(l["review_total"] for l in lessons),
        "unanswered": unanswered,
        "assessment_available": not unanswered
        and status(enrollment) == "active",
    }
