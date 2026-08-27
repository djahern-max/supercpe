"""The qualified assessment engine (6.01.2).

The assessment is a form submitted once, not a sequence of graded
questions: 6.01.2 sub-ii (no test bank) forbids feedback on a failed
assessment, and pass or fail is only known after the whole assessment is
scored — so no per-question verdict may exist client-side while an attempt
is open, and none may ever be shown for a failed attempt. `result` is the
single place that rule is enforced; everything a participant sees about an
attempt comes from it.

superCPE serves no test bank: every assessment question is served every
time, so sub-ii's failed-assessment branch always applies.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.assessment import PASSING_PCT, RETAKES_ALLOWED
from app.models.attempt import Attempt, AttemptAnswer
from app.models.course import Course
from app.models.question import Question
from app.services import credit, readiness
from app.services import questions as questions_service

_PCT_2DP = Decimal("0.01")


class AssessmentRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def questions_for(db: Session, course: Course) -> list[Question]:
    """The questions in the order the assessment serves them: package
    position, then question position, choices as stored. No shuffling:
    auditability of "what was asked" beats the marginal integrity gain,
    and a shuffle can be added later with the order stored per attempt."""
    return questions_service.course_assessment_questions(db, course)


def open_attempt(db: Session, course: Course, preview_id: str) -> Attempt | None:
    return db.scalar(
        select(Attempt).where(
            Attempt.course_id == course.id,
            Attempt.preview_id == preview_id,
            Attempt.status == "open",
        )
    )


def start(db: Session, course: Course, preview_id: str) -> Attempt:
    """Open an attempt. Refuses while the course's credit is stale or any
    block readiness finding exists: an assessment that does not satisfy
    6.01.2 is not a qualified assessment and grading against it would prove
    nothing."""
    if credit.is_stale(course):
        raise AssessmentRuleViolation(
            [
                "the course's credit measurement is stale "
                f"({credit.stale_reason(course)}); the assessment cannot "
                "be taken until it is recomputed"
            ]
        )
    blocks = [f for f in readiness.check(db, course) if f.level == "block"]
    if blocks:
        raise AssessmentRuleViolation(
            ["the assessment is not well-formed yet: " + f.message for f in blocks]
        )
    if open_attempt(db, course, preview_id) is not None:
        raise AssessmentRuleViolation(
            ["an attempt is already open; submit or abandon it first"]
        )

    questions = questions_for(db, course)
    if not questions:
        raise AssessmentRuleViolation(
            ["the course has no assessment questions"]
        )
    attempt = Attempt(
        course_id=course.id,
        preview_id=preview_id,
        is_preview=True,
        status="open",
        passing_pct=PASSING_PCT,
        question_count=len(questions),
        package_versions=[
            {"package_id": cl.package_id, "version": cl.package.version}
            for cl in sorted(course.lessons, key=lambda cl: cl.position)
        ],
    )
    db.add(attempt)
    db.commit()
    return attempt


def _validated_choices(
    db: Session, attempt: Attempt, answers: dict[int, int]
) -> dict[int, "object"]:
    """Map question_id -> Choice row for the given answers, refusing ids
    that are not this assessment's questions or their choices."""
    questions = {q.id: q for q in questions_for(db, attempt.course)}
    errors = []
    chosen = {}
    for question_id, choice_id in answers.items():
        question = questions.get(question_id)
        if question is None:
            errors.append(
                f"question {question_id} is not on this assessment"
            )
            continue
        choice = next((c for c in question.choices if c.id == choice_id), None)
        if choice is None:
            errors.append(
                f"choice {choice_id} is not a choice of question {question_id}"
            )
            continue
        chosen[question_id] = choice
    if errors:
        raise AssessmentRuleViolation(errors)
    return chosen


def _write_answers(db: Session, attempt: Attempt, chosen: dict) -> None:
    now = datetime.now(timezone.utc)
    existing = {a.question_id: a for a in attempt.answers}
    for question_id, choice in chosen.items():
        answer = existing.get(question_id)
        if answer is None:
            attempt.answers.append(
                AttemptAnswer(
                    question_id=question_id,
                    choice_id=choice.id,
                    answered_at=now,
                )
            )
        elif answer.choice_id != choice.id:
            answer.choice_id = choice.id
            answer.answered_at = now


def _require_open(attempt: Attempt) -> None:
    if attempt.status != "open":
        raise AssessmentRuleViolation(
            [f"the attempt is already {attempt.status}"]
        )


def save_answers(db: Session, attempt: Attempt, answers: dict[int, int]) -> Attempt:
    """Persist partial answers so a refresh does not lose work. No grading:
    is_correct stays null while the attempt is open."""
    _require_open(attempt)
    _write_answers(db, attempt, _validated_choices(db, attempt, answers))
    db.commit()
    return attempt


def grade(correct_count: int, question_count: int) -> tuple[Decimal, bool]:
    """(score_pct, passed). Pass/fail compares the exact ratio against the
    threshold — correct x 100 >= passing x total — never the two-decimal
    display score, so rounding can never lift a 69.996 over the 70 floor."""
    exact = Decimal(correct_count * 100) / Decimal(question_count)
    passed = Decimal(correct_count * 100) >= PASSING_PCT * question_count
    return exact.quantize(_PCT_2DP), passed


def submit(db: Session, attempt: Attempt, answers: dict[int, int]) -> Attempt:
    """Grade the whole assessment at once. Every question must be answered;
    the submission is the complete form (6.01.2 sub-ii)."""
    _require_open(attempt)
    chosen = _validated_choices(db, attempt, answers)
    questions = questions_for(db, attempt.course)
    unanswered = [q for q in questions if q.id not in chosen]
    if unanswered:
        raise AssessmentRuleViolation(
            [
                f"{len(unanswered)} of {len(questions)} questions are "
                "unanswered; the assessment is submitted whole"
            ]
        )
    _write_answers(db, attempt, chosen)
    for answer in attempt.answers:
        answer.is_correct = chosen[answer.question_id].is_correct
    correct_count = sum(1 for c in chosen.values() if c.is_correct)
    score_pct, passed = grade(correct_count, len(questions))
    attempt.correct_count = correct_count
    attempt.score_pct = score_pct
    attempt.status = "passed" if passed else "failed"
    attempt.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return attempt


def abandon(db: Session, attempt: Attempt) -> Attempt:
    """An open attempt the participant walks away from becomes a failed
    attempt with no score. Retained like every other attempt."""
    _require_open(attempt)
    attempt.status = "failed"
    db.commit()
    return attempt


def result(attempt: Attempt) -> dict:
    """Everything a participant may see about an attempt — the 6.01.2
    sub-ii rule lives here.

    Passed: the per-question record (chosen choice, correct choice,
    verdict, feedback). Failed: score, status, question count, correct
    count, and the retake affordance — nothing per question, because "may
    not provide feedback" is absolute and a count of correct answers is the
    outer limit of what a score already reveals. Open: the saved answers,
    with no correctness anywhere (none exists yet)."""
    base = {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "question_count": attempt.question_count,
        "passing_pct": str(attempt.passing_pct),
        "started_at": attempt.started_at.isoformat(),
    }
    if attempt.status == "open":
        return base | {
            "answers": {
                str(a.question_id): a.choice_id for a in attempt.answers
            }
        }

    base |= {
        "score_pct": str(attempt.score_pct)
        if attempt.score_pct is not None
        else None,
        "correct_count": attempt.correct_count,
        "submitted_at": attempt.submitted_at.isoformat()
        if attempt.submitted_at
        else None,
    }
    if attempt.status == "failed":
        return base | {"retakes_allowed": RETAKES_ALLOWED}

    package_order = [p["package_id"] for p in attempt.package_versions]
    answers = sorted(
        attempt.answers,
        key=lambda a: (
            package_order.index(a.question.package_id),
            a.question.position,
        ),
    )
    return base | {
        "questions": [
            {
                "question_id": answer.question_id,
                "stem": answer.question.stem,
                "choices": [
                    {"choice_id": c.id, "text": c.text}
                    for c in answer.question.choices
                ],
                "chosen_choice_id": answer.choice_id,
                "correct_choice_id": next(
                    c.id for c in answer.question.choices if c.is_correct
                ),
                "is_correct": answer.is_correct,
                "feedback": answer.question.feedback,
            }
            for answer in answers
        ]
    }
