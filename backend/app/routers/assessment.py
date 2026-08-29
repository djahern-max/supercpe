"""The qualified assessment endpoints (6.01.2).

Behind admin and reviewer sessions for now, like the player: attempts are
preview attempts keyed by an opaque X-Preview-Id header the frontend
generates once per session. Feature 010 re-gates these routes behind
enrollment; the preview path stays for admins and reviewers.

The two result-serving endpoints return `assessment.result`'s dict
verbatim, with no response model: the sub-ii feedback rule is enforced by
what that dict contains, and a schema with optional fields could leak
key names into a failed attempt's payload.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_role
from app.constants.assessment import PASSING_PCT, RETAKES_ALLOWED
from app.db import get_db
from app.models.attempt import Attempt
from app.models.course import Course
from app.schemas.assessment import (
    AdminAttempt,
    AdminAttemptAnswer,
    AnswersRequest,
    AnswersSaved,
    AssessmentChoice,
    AssessmentInfo,
    AssessmentQuestion,
    AttemptStarted,
)
from app.schemas.package import ValidationErrors
from app.services import assessment, courses
from app.services.assessment import AssessmentRuleViolation

router = APIRouter(
    prefix="/courses",
    dependencies=[Depends(require_role("admin", "reviewer"))],
)
admin_router = APIRouter(
    prefix="/admin/courses", dependencies=[Depends(require_role("admin"))]
)


def _get_course_or_404(db: Session, course_code: str) -> Course:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _get_attempt_or_404(
    db: Session, course: Course, attempt_id: int, preview_id: str
) -> Attempt:
    attempt = db.get(Attempt, attempt_id)
    if (
        attempt is None
        or attempt.course_id != course.id
        or attempt.preview_id != preview_id
    ):
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt


def _require_preview_id(x_preview_id: str | None) -> str:
    if not x_preview_id:
        raise HTTPException(
            status_code=422, detail="X-Preview-Id header is required"
        )
    return x_preview_id


def _violation_response(violation: AssessmentRuleViolation) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": violation.errors})


@router.get("/{course_code}/assessment", response_model=AssessmentInfo)
def get_assessment(
    course_code: str,
    db: Session = Depends(get_db),
    x_preview_id: str | None = Header(default=None),
):
    """The assessment as a participant sees it before and while taking it:
    questions and choices, never answers, never feedback."""
    course = _get_course_or_404(db, course_code)
    open_attempt = (
        assessment.open_attempt(db, course, x_preview_id)
        if x_preview_id
        else None
    )
    questions = assessment.questions_for(db, course)
    return AssessmentInfo(
        course_code=course.course_code,
        title=course.title,
        question_count=len(questions),
        passing_pct=str(PASSING_PCT),
        retakes_allowed=RETAKES_ALLOWED,
        open_attempt_id=open_attempt.id if open_attempt else None,
        questions=[
            AssessmentQuestion(
                question_id=q.id,
                stem=q.stem,
                choices=[
                    AssessmentChoice(choice_id=c.id, text=c.text)
                    for c in q.choices
                ],
            )
            for q in questions
        ],
    )


@router.post(
    "/{course_code}/assessment/attempts",
    response_model=AttemptStarted,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def start_attempt(
    course_code: str,
    db: Session = Depends(get_db),
    x_preview_id: str | None = Header(default=None),
):
    course = _get_course_or_404(db, course_code)
    preview_id = _require_preview_id(x_preview_id)
    try:
        attempt = assessment.start(db, course, preview_id)
    except AssessmentRuleViolation as violation:
        return _violation_response(violation)
    return AttemptStarted(
        attempt_id=attempt.id,
        status=attempt.status,
        question_count=attempt.question_count,
        passing_pct=str(attempt.passing_pct),
        started_at=attempt.started_at,
    )


@router.put(
    "/{course_code}/assessment/attempts/{attempt_id}/answers",
    response_model=AnswersSaved,
    responses={422: {"model": ValidationErrors}},
)
def save_answers(
    course_code: str,
    attempt_id: int,
    payload: AnswersRequest,
    db: Session = Depends(get_db),
    x_preview_id: str | None = Header(default=None),
):
    course = _get_course_or_404(db, course_code)
    preview_id = _require_preview_id(x_preview_id)
    attempt = _get_attempt_or_404(db, course, attempt_id, preview_id)
    try:
        attempt = assessment.save_answers(db, attempt, payload.answers)
    except AssessmentRuleViolation as violation:
        return _violation_response(violation)
    return AnswersSaved(
        attempt_id=attempt.id,
        answered=len(attempt.answers),
        question_count=attempt.question_count,
    )


@router.post(
    "/{course_code}/assessment/attempts/{attempt_id}/submit",
    responses={422: {"model": ValidationErrors}},
)
def submit_attempt(
    course_code: str,
    attempt_id: int,
    payload: AnswersRequest,
    db: Session = Depends(get_db),
    x_preview_id: str | None = Header(default=None),
):
    course = _get_course_or_404(db, course_code)
    preview_id = _require_preview_id(x_preview_id)
    attempt = _get_attempt_or_404(db, course, attempt_id, preview_id)
    try:
        attempt = assessment.submit(db, attempt, payload.answers)
    except AssessmentRuleViolation as violation:
        return _violation_response(violation)
    return assessment.result(attempt)


@router.get("/{course_code}/assessment/attempts/{attempt_id}")
def get_attempt(
    course_code: str,
    attempt_id: int,
    db: Session = Depends(get_db),
    x_preview_id: str | None = Header(default=None),
):
    course = _get_course_or_404(db, course_code)
    preview_id = _require_preview_id(x_preview_id)
    attempt = _get_attempt_or_404(db, course, attempt_id, preview_id)
    return assessment.result(attempt)


@admin_router.get(
    "/{course_code}/attempts", response_model=list[AdminAttempt]
)
def list_attempts(course_code: str, db: Session = Depends(get_db)):
    """Every attempt with per-answer detail. The admin may see everything —
    including which answers a failed attempt got wrong; the participant
    may not (6.01.2 sub-ii binds what the sponsor shows the test taker,
    not what the sponsor itself records)."""
    course = _get_course_or_404(db, course_code)
    attempts = db.scalars(
        select(Attempt)
        .where(Attempt.course_id == course.id)
        .order_by(Attempt.started_at.desc(), Attempt.id.desc())
    )
    return [
        AdminAttempt(
            id=attempt.id,
            is_preview=attempt.is_preview,
            preview_id=attempt.preview_id,
            enrollment_id=attempt.enrollment_id,
            status=attempt.status,
            score_pct=str(attempt.score_pct)
            if attempt.score_pct is not None
            else None,
            passing_pct=str(attempt.passing_pct),
            question_count=attempt.question_count,
            correct_count=attempt.correct_count,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            package_versions=attempt.package_versions,
            answers=[
                AdminAttemptAnswer(
                    question_id=answer.question_id,
                    question_key=answer.question.question_key,
                    stem=answer.question.stem,
                    chosen_choice_id=answer.choice_id,
                    chosen_text=answer.choice.text,
                    correct_choice_id=next(
                        c.id for c in answer.question.choices if c.is_correct
                    ),
                    is_correct=answer.is_correct,
                    answered_at=answer.answered_at,
                )
                for answer in answer_rows(attempt)
            ],
        )
        for attempt in attempts
    ]


def answer_rows(attempt: Attempt):
    package_order = [p["package_id"] for p in attempt.package_versions]
    return sorted(
        attempt.answers,
        key=lambda a: (
            package_order.index(a.question.package_id)
            if a.question.package_id in package_order
            else len(package_order),
            a.question.position,
        ),
    )
