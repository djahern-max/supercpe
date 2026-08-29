"""Program evaluations (4.04, 4.04.1) and the sponsor's review of their
results (4.04.2).

Evaluations are solicited, never required: `solicit` says whether the
prompt should still appear, and a participant who declines loses nothing —
the certificate never waits on an evaluation. One evaluation per
completion, ever. Reviews of results are dated, snapshotted, append-only
records; "periodically" is `EVALUATION_REVIEW_DAYS`, superCPE's own
concretion, reported as a warn finding and never enforced.
"""

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.evaluation import (
    EVALUATION_REVIEW_DAYS,
    PROMPTS,
    RATED_ELEMENTS,
    SCALE_MAX,
    SCALE_MIN,
    SOLICIT_UNTIL_DAYS,
)
from app.models.account import Account
from app.models.course import Course
from app.models.enrollment import Completion, Enrollment
from app.models.evaluation import Evaluation, EvaluationReview
from app.services import enrollments as enrollments_service

_MEAN_2DP = Decimal("0.01")


class EvaluationRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_for_completion(db: Session, completion: Completion) -> Evaluation | None:
    return db.scalar(
        select(Evaluation).where(Evaluation.completion_id == completion.id)
    )


def solicit(db: Session, completion: Completion) -> bool:
    """Whether the evaluation prompt should still appear: no evaluation
    yet, and within SOLICIT_UNTIL_DAYS of completion."""
    if _now() > completion.completed_at + timedelta(days=SOLICIT_UNTIL_DAYS):
        return False
    return get_for_completion(db, completion) is None


def submit(
    db: Session,
    completion: Completion,
    ratings: dict[str, int],
    comments: str = "",
) -> Evaluation:
    """Record the one evaluation of this completion. Refuses a second, a
    rating outside the scale, and any attempt to rate item 5 (instructors:
    not applicable to self study, never asked, never accepted)."""
    errors = []
    if get_for_completion(db, completion) is not None:
        errors.append(
            "an evaluation is already recorded for this completion; "
            "evaluations cannot be changed or resubmitted"
        )
    if "instructors_effective" in ratings:
        errors.append(
            "instructors_effective cannot be rated: self study programs "
            "have no instructors (4.04.1 item 5 is not applicable)"
        )
    for element in RATED_ELEMENTS:
        value = ratings.get(element)
        if value is None:
            errors.append(f"{element} is missing")
        elif not (SCALE_MIN <= value <= SCALE_MAX):
            errors.append(
                f"{element} must be between {SCALE_MIN} and {SCALE_MAX}, "
                f"not {value}"
            )
    unknown = set(ratings) - set(RATED_ELEMENTS) - {"instructors_effective"}
    if unknown:
        errors.append(f"unknown elements: {', '.join(sorted(unknown))}")
    if errors:
        raise EvaluationRuleViolation(errors)

    evaluation = Evaluation(
        completion_id=completion.id,
        submitted_at=_now(),
        comments=comments,
        objectives_snapshot=_objectives_snapshot(db, completion.enrollment),
        **{element: ratings[element] for element in RATED_ELEMENTS},
    )
    db.add(evaluation)
    db.commit()
    return evaluation


def _objectives_snapshot(db: Session, enrollment: Enrollment) -> list:
    """The objectives the participant was rating, from the pinned package
    versions — what they were actually taught, whatever the course's
    lessons say by now."""
    return [
        {
            "lesson_id": package.lesson_id,
            "version": package.version,
            "objectives": package.manifest["learning_objectives"],
        }
        for package in enrollments_service.packages_for(db, enrollment)
    ]


def for_course(db: Session, course: Course) -> list[Evaluation]:
    """Every evaluation of the course, oldest first."""
    return list(
        db.scalars(
            select(Evaluation)
            .join(Completion, Evaluation.completion_id == Completion.id)
            .join(Enrollment, Completion.enrollment_id == Enrollment.id)
            .where(Enrollment.course_id == course.id)
            .order_by(Evaluation.submitted_at, Evaluation.id)
        )
    )


def summary(db: Session, course: Course) -> dict:
    """n, mean and distribution per rated element, and the comments in
    submitted order. Means are Decimal, serialized as strings. Item 5 is
    stated as not applicable rather than omitted."""
    rows = for_course(db, course)
    elements = {}
    for element in RATED_ELEMENTS:
        values = [getattr(row, element) for row in rows]
        distribution = {
            str(point): sum(1 for v in values if v == point)
            for point in range(SCALE_MIN, SCALE_MAX + 1)
        }
        mean = (
            str(
                (Decimal(sum(values)) / Decimal(len(values))).quantize(
                    _MEAN_2DP, rounding=ROUND_HALF_UP
                )
            )
            if values
            else None
        )
        elements[element] = {
            "prompt": PROMPTS[element],
            "mean": mean,
            "distribution": distribution,
        }
    return {
        "n": len(rows),
        "elements": elements,
        "instructors_effective": "not applicable (self study)",
        "comments": [
            {
                "submitted_at": row.submitted_at.astimezone(
                    timezone.utc
                ).isoformat(),
                "comments": row.comments,
            }
            for row in rows
            if row.comments.strip()
        ],
    }


def record_review(
    db: Session,
    course: Course,
    account: Account,
    note: str = "",
    informed_developer: bool = False,
) -> EvaluationReview:
    """The 4.04.2 record: the summary as of now, snapshotted and dated."""
    review = EvaluationReview(
        course_id=course.id,
        reviewed_at=_now(),
        reviewed_by_account_id=account.id,
        summary_snapshot=summary(db, course),
        note=note,
        informed_developer=informed_developer,
    )
    db.add(review)
    db.commit()
    return review


def reviews_for_course(db: Session, course: Course) -> list[EvaluationReview]:
    """Newest first."""
    return list(
        db.scalars(
            select(EvaluationReview)
            .where(EvaluationReview.course_id == course.id)
            .order_by(
                EvaluationReview.reviewed_at.desc(), EvaluationReview.id.desc()
            )
        )
    )


def review_due(db: Session, course: Course) -> dict | None:
    """The `evaluation_review_due` facts, or None while nothing is due:
    an evaluation not covered by any review has waited longer than
    EVALUATION_REVIEW_DAYS. Recording a review covers everything submitted
    up to its `reviewed_at`."""
    latest = next(iter(reviews_for_course(db, course)), None)
    since = latest.reviewed_at if latest else None
    waiting = [
        row
        for row in for_course(db, course)
        if since is None or row.submitted_at > since
    ]
    deadline = _now() - timedelta(days=EVALUATION_REVIEW_DAYS)
    overdue = [row for row in waiting if row.submitted_at < deadline]
    if not overdue:
        return None
    return {
        "unreviewed": len(waiting),
        "oldest_submitted_at": min(row.submitted_at for row in overdue),
        "last_reviewed_at": since,
    }
