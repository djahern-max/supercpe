"""Readiness checklist: what stands between a course and publishing.

`check` only reports — with one exception: `assessment.start` refuses to
open an attempt while any block finding exists, because an assessment that
does not satisfy 6.01.2 is not a qualified assessment. Feature 008 turns
block findings into a publish refusal. 006 contributed the credit and
5.01.2.1 review-question findings; 007 the 6.01.2 assessment findings.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.assessment import OBJECTIVE_COVERAGE_PCT
from app.constants.question_minimums import (
    COUNTING_MIN_CHOICES,
    MIN_CHOICES_ASSESSMENT,
    required_assessment_questions,
    required_review_questions,
)
from app.models.course import Course
from app.services import courses as courses_service
from app.services import credit
from app.services import questions as questions_service


@dataclass
class Finding:
    code: str
    level: str  # "block" | "warn"
    message: str


@dataclass
class ReviewCounts:
    """The 5.01.2.1 comparison, also shown when it is satisfied and no
    finding exists. `required` is None while the credit is stale: without a
    credit there is nothing to derive the requirement from."""

    counting: int
    required: int | None


def review_counts(db: Session, course: Course) -> ReviewCounts:
    counting = sum(
        1
        for q in questions_service.course_review_questions(db, course)
        if questions_service.counts_toward_minimum(q)
    )
    required = (
        required_review_questions(course.credit_award)
        if not credit.is_stale(course)
        else None
    )
    return ReviewCounts(counting=counting, required=required)


def check(db: Session, course: Course) -> list[Finding]:
    findings: list[Finding] = []

    fresh_credit = not credit.is_stale(course)
    if not fresh_credit:
        findings.append(
            Finding(
                code="credit_missing",
                level="block",
                message=(
                    "The course has no fresh credit measurement "
                    f"({credit.stale_reason(course)}); the review question "
                    "minimum cannot be checked without one."
                ),
            )
        )

    review_questions = questions_service.course_review_questions(db, course)
    counting = [
        q for q in review_questions if questions_service.counts_toward_minimum(q)
    ]

    if fresh_credit:
        required = required_review_questions(course.credit_award)
        if len(counting) < required:
            findings.append(
                Finding(
                    code="review_minimum",
                    level="block",
                    message=(
                        f"{len(counting)} counting review questions, but "
                        f"{required} are required for {course.credit_award} "
                        "CPE credit (5.01.2.1)."
                    ),
                )
            )

    # 5.01.2.1 requires review questions "throughout the program"; a lesson
    # with none cannot satisfy that, however many its neighbors carry.
    question_counts = {
        lesson.package_id: 0 for lesson in course.lessons
    }
    for question in review_questions:
        question_counts[question.package_id] += 1
    empty = [
        lesson.package.lesson_id
        for lesson in sorted(course.lessons, key=lambda cl: cl.position)
        if question_counts[lesson.package_id] == 0
    ]
    if empty:
        findings.append(
            Finding(
                code="review_placement",
                level="warn",
                message=(
                    "Lessons with no review question at all: "
                    f"{', '.join(empty)}. 5.01.2.1 places review questions "
                    "throughout the program."
                ),
            )
        )

    two_choice = [
        q.question_key
        for q in review_questions
        if len(q.choices) < COUNTING_MIN_CHOICES
    ]
    if two_choice:
        findings.append(
            Finding(
                code="review_two_choice",
                level="warn",
                message=(
                    "Two-choice review questions do not count toward the "
                    f"5.01.2.1 minimum: {', '.join(two_choice)}."
                ),
            )
        )

    findings += _assessment_findings(db, course, fresh_credit, review_questions)

    return findings


def _assessment_findings(
    db: Session, course: Course, fresh_credit: bool, review_questions
) -> list[Finding]:
    """The 6.01.2 findings: question minimum, forced choice, duplicates,
    and objective coverage. All block: an assessment that fails any of them
    is not a qualified assessment."""
    findings: list[Finding] = []
    lesson_of = {cl.package_id: cl.package.lesson_id for cl in course.lessons}
    assessment_questions = questions_service.course_assessment_questions(
        db, course
    )

    counting = [
        q
        for q in assessment_questions
        if len(q.choices) >= MIN_CHOICES_ASSESSMENT
    ]
    if fresh_credit:
        required = required_assessment_questions(course.credit_award)
        if len(counting) < required:
            findings.append(
                Finding(
                    code="assessment_minimum",
                    level="block",
                    message=(
                        f"{len(counting)} assessment questions, but "
                        f"{required} are required for {course.credit_award} "
                        "CPE credit (6.01.2)."
                    ),
                )
            )

    # Ingest already refuses two-choice questions of any kind, so this can
    # only arise from a fixture or a bypassed validator; kept as defense in
    # depth because 6.01.2 forbids forced choice outright.
    forced = [
        f"{q.question_key} ({lesson_of[q.package_id]})"
        for q in assessment_questions
        if len(q.choices) < MIN_CHOICES_ASSESSMENT
    ]
    if forced:
        findings.append(
            Finding(
                code="assessment_forced_choice",
                level="block",
                message=(
                    "Forced-choice questions are not permissible on the "
                    f"qualified assessment (6.01.2): {', '.join(forced)}."
                ),
            )
        )

    review_stems = {}
    for q in review_questions:
        review_stems.setdefault(questions_service.normalized_stem(q.stem), q)
    duplicates = []
    for q in assessment_questions:
        twin = review_stems.get(questions_service.normalized_stem(q.stem))
        if twin is not None:
            duplicates.append(
                f"assessment {q.question_key} ({lesson_of[q.package_id]}) "
                f"duplicates review {twin.question_key} "
                f"({lesson_of[twin.package_id]})"
            )
    if duplicates:
        findings.append(
            Finding(
                code="assessment_duplicate",
                level="block",
                message=(
                    "Duplicate review and assessment questions are not "
                    f"allowed (6.01.2): {'; '.join(duplicates)}."
                ),
            )
        )

    # Objective ids are unique only within a package, so coverage is keyed
    # by (package_id, objective id).
    all_objectives = {
        (group["package_id"], objective["id"]): group["lesson_id"]
        for group in courses_service.course_objectives(course)
        for objective in group["objectives"]
    }
    covered = {
        (q.package_id, key)
        for q in assessment_questions
        for key in q.objective_keys
        if (q.package_id, key) in all_objectives
    }
    if all_objectives:
        coverage_pct = Decimal(len(covered) * 100) / len(all_objectives)
        if coverage_pct < OBJECTIVE_COVERAGE_PCT:
            uncovered = [
                f"{key} ({lesson_id})"
                for (package_id, key), lesson_id in all_objectives.items()
                if (package_id, key) not in covered
            ]
            findings.append(
                Finding(
                    code="objective_coverage",
                    level="block",
                    message=(
                        f"The assessment measures {len(covered)} of "
                        f"{len(all_objectives)} learning objectives; 6.01.2 "
                        f"requires at least {OBJECTIVE_COVERAGE_PCT} "
                        "percent. Uncovered: "
                        f"{', '.join(uncovered)}."
                    ),
                )
            )

    return findings
