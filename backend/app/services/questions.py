"""Normalize a package's questions.json into the questions/choices tables.

`normalize` is called by `packages.ingest` inside the ingest transaction, so
a package row never exists without its question rows. The rows carry no
credit or score; they exist so review questions can be counted against
5.01.2.1 minimums, placed in the player, and graded server-side without the
answer key ever leaving the database.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.constants.question_minimums import COUNTING_MIN_CHOICES
from app.models.course import Course
from app.models.lesson_package import LessonPackage
from app.models.question import Choice, Question


def normalize(db: Session, package: LessonPackage) -> list[Question]:
    """Write question and choice rows from the package's stored questions
    JSON. Flushes but does not commit; the caller owns the transaction."""
    rows = []
    for position, q in enumerate(package.questions, start=1):
        correct = [c["id"] for c in q["choices"] if c["id"] == q["correct"]]
        if len(correct) != 1:
            # Validation (rule 14) refuses this before ingest; a second
            # guard here keeps the exactly-one-correct invariant local.
            raise ValueError(
                f"question {q['id']}: expected exactly one correct choice, "
                f"found {len(correct)}"
            )
        question = Question(
            package_id=package.id,
            question_key=q["id"],
            kind=q["kind"],
            # Exactly one placement per review question, whichever medium
            # the package is (5.01.2.1); the CHECK on the table enforces it.
            after_block=q.get("after_block"),
            after_section=q.get("after_section"),
            position=position,
            stem=q["stem"],
            feedback=q["feedback"],
            objective_keys=q["objective_ids"],
            choices=[
                Choice(
                    choice_key=c["id"],
                    text=c["text"],
                    is_correct=c["id"] == q["correct"],
                    position=choice_position,
                )
                for choice_position, c in enumerate(q["choices"], start=1)
            ],
        )
        db.add(question)
        rows.append(question)
    db.flush()
    return rows


def for_package(db: Session, package_id: int) -> list[Question]:
    return list(
        db.scalars(
            select(Question)
            .where(Question.package_id == package_id)
            .options(selectinload(Question.choices))
            .order_by(Question.position)
        )
    )


def get_question(
    db: Session, package_id: int, question_key: str
) -> Question | None:
    return db.scalar(
        select(Question)
        .where(
            Question.package_id == package_id,
            Question.question_key == question_key,
        )
        .options(selectinload(Question.choices))
    )


def counts_toward_minimum(question: Question) -> bool:
    """5.01.2.1: only review questions with more than two choices count."""
    return (
        question.kind == "review"
        and len(question.choices) >= COUNTING_MIN_CHOICES
    )


def course_review_questions(db: Session, course: Course) -> list[Question]:
    """The course's review questions: those of its attached packages'
    current versions, in lesson order then question order."""
    return _course_questions(db, course, "review")


def course_assessment_questions(db: Session, course: Course) -> list[Question]:
    """The course's qualified assessment questions, in lesson order then
    question order — the order the assessment serves them (no test bank,
    no shuffling: every question, every time)."""
    return _course_questions(db, course, "assessment")


def _course_questions(db: Session, course: Course, kind: str) -> list[Question]:
    rows = []
    for lesson in sorted(course.lessons, key=lambda cl: cl.position):
        rows += [
            q for q in for_package(db, lesson.package_id) if q.kind == kind
        ]
    return rows


def normalized_stem(stem: str) -> str:
    """The form in which two stems count as duplicates for 6.01.2's "duplicate
    review and qualified assessment questions are not allowed": lowercase,
    whitespace collapsed, trailing punctuation stripped."""
    collapsed = re.sub(r"\s+", " ", stem.strip().lower())
    return collapsed.rstrip(".?!,;:…").rstrip()
