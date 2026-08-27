"""Readiness checklist: what stands between a course and publishing.

`check` only reports. Feature 008 turns "block" findings into a publish
refusal; nothing here refuses anything. This feature contributes the credit
and 5.01.2.1 review-question findings; later features append their own.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.constants.question_minimums import (
    COUNTING_MIN_CHOICES,
    required_review_questions,
)
from app.models.course import Course
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

    return findings
