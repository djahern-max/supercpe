"""The participant surface: everything behind an enrollment.

Every route takes the account from the session and refuses a foreign
enrollment with 404, not 403 — whether an enrollment exists is nobody
else's business. The player and assessment here serve the *pinned* package
versions; the admin/reviewer preview endpoints (006/007) are untouched and
keep serving the course's current content.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_role
from app.constants.assessment import PASSING_PCT, RETAKES_ALLOWED
from app.constants.storage import VIDEO_URL_SECONDS
from app.constants.evaluation import (
    PROMPTS,
    RATED_ELEMENTS,
    SCALE_MAX,
    SCALE_MIN,
)
from app.db import get_db
from app.models.account import Account
from app.models.attempt import Attempt
from app.models.enrollment import Enrollment
from app.schemas.assessment import (
    AnswersRequest,
    AnswersSaved,
    AssessmentChoice,
    AssessmentQuestion,
    AttemptStarted,
)
from app.schemas.enrollment import (
    MyAssessmentInfo,
    MyCompletionOut,
    MyEnrollmentDetail,
    MyEnrollmentSummary,
    MyLessonProgress,
    MyPlayLesson,
    ProgressOut,
    ProgressUpdate,
)
from app.schemas.evaluation import (
    EvaluationPrompt,
    EvaluationSubmit,
    MyEvaluationInfo,
)
from app.schemas.package import ValidationErrors
from app.schemas.player import (
    PlayBlock,
    PlayChoice,
    PlayQuestion,
    ReviewAnswer,
    ReviewResult,
)
from app.services import assessment, completions, enrollments, evaluations
from app.services import questions as questions_service
from app.services.assessment import AssessmentRuleViolation
from app.services.completions import CreditStale, IssuanceBlocked
from app.services.evaluations import EvaluationRuleViolation
from app.storage import Storage, get_storage

router = APIRouter(prefix="/my")

participant = require_role("participant")

# Watching to within a second of the end counts as watching the lesson;
# timeupdate granularity means the very last tick may never be reported.
_WATCHED_TOLERANCE_SECONDS = 1


def _get_enrollment_or_404(
    db: Session, account: Account, enrollment_id: int
) -> Enrollment:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.account_id != account.id:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment


def _refuse_if_voided(enrollment: Enrollment) -> None:
    """018: a voided enrollment (refund granted, access ended by an
    admin per the refund policy) serves no video and grades nothing —
    unlike expired, where the participant may still review what they
    paid for. The enrollment still appears in listings with its derived
    status; only the content routes refuse."""
    if enrollments.status(enrollment) == "voided":
        raise HTTPException(
            status_code=403, detail="This enrollment has been voided"
        )


def _get_pinned_package_or_404(db: Session, enrollment: Enrollment, package_id: int):
    package = enrollments.pinned_package(db, enrollment, package_id)
    if package is None:
        raise HTTPException(
            status_code=404, detail="Lesson not part of this enrollment"
        )
    return package


def _violation_response(violation: AssessmentRuleViolation) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": violation.errors})


def _completion_out(db: Session, enrollment: Enrollment) -> MyCompletionOut | None:
    completion = enrollment.completion
    if completion is None:
        return None
    return MyCompletionOut(
        completion_id=completion.id,
        completed_at=completion.completed_at,
        credit_awarded=str(completion.credit_awarded),
        field_of_study=completion.field_of_study,
        certificate_number=completion.certificate_number,
        certificate_ready=completions.certificate_ready(db, completion),
        evaluation_requested=evaluations.solicit(db, completion),
    )


def _unavailable_reasons(
    db: Session, enrollment: Enrollment, progress: dict
) -> list[str]:
    status = enrollments.status(enrollment)
    reasons = []
    if status == "expired":
        reasons.append(
            "The enrollment expired on "
            f"{enrollment.expires_at.date().isoformat()}."
        )
    if status == "completed":
        reasons.append("The course is completed.")
    if status == "voided":
        reasons.append("This enrollment has been voided.")
    for group in progress["unanswered"]:
        reasons.append(
            f"Unanswered review questions in {group['lesson_id']}: "
            f"{', '.join(group['question_keys'])}."
        )
    if (
        status == "active"
        and enrollments.retakes_remaining(db, enrollment) == 0
    ):
        reasons.append("No re-takes left on this enrollment.")
    return reasons


def _summary_fields(db: Session, enrollment: Enrollment) -> dict:
    progress = enrollments.progress(db, enrollment)
    open_attempt = assessment.open_attempt_for_enrollment(db, enrollment)
    course = enrollment.course
    retakes = enrollments.retakes_remaining(db, enrollment)
    return {
        "enrollment_id": enrollment.id,
        "course_code": course.course_code,
        "title": course.title,
        "status": enrollments.status(enrollment),
        "enrolled_at": enrollment.enrolled_at,
        "expires_at": enrollment.expires_at,
        "credit": str(course.credit_award)
        if course.credit_award is not None
        else None,
        "field_of_study": course.field_of_study,
        "lessons_total": len(progress["lessons"]),
        "lessons_watched": sum(
            1
            for lesson in progress["lessons"]
            if lesson["furthest_seconds"]
            >= lesson["duration_seconds"] - _WATCHED_TOLERANCE_SECONDS
        ),
        "review_answered": progress["review_answered"],
        "review_total": progress["review_total"],
        "assessment_available": progress["assessment_available"] and retakes > 0,
        "retakes_remaining": retakes,
        "failed_attempts": enrollments.failed_attempts(db, enrollment),
        "open_attempt_id": open_attempt.id if open_attempt else None,
        "completion": _completion_out(db, enrollment),
        "_progress": progress,
    }


@router.get("/courses", response_model=list[MyEnrollmentSummary])
def my_courses(
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    """The participant home: every enrollment, newest first."""
    summaries = []
    for enrollment in enrollments.list_for_account(db, account):
        fields = _summary_fields(db, enrollment)
        fields.pop("_progress")
        summaries.append(MyEnrollmentSummary(**fields))
    return summaries


@router.get("/enrollments/{enrollment_id}", response_model=MyEnrollmentDetail)
def enrollment_detail(
    enrollment_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    fields = _summary_fields(db, enrollment)
    progress = fields.pop("_progress")
    course = enrollment.course
    return MyEnrollmentDetail(
        **fields,
        description=course.description,
        knowledge_level=course.knowledge_level,
        prerequisites=course.prerequisites,
        advance_preparation=course.advance_preparation,
        lessons=[MyLessonProgress(**lesson) for lesson in progress["lessons"]],
        assessment_unavailable_reasons=_unavailable_reasons(
            db, enrollment, progress
        ),
    )


@router.get(
    "/enrollments/{enrollment_id}/lessons/{package_id}/play",
    response_model=MyPlayLesson,
)
def play_lesson(
    enrollment_id: int,
    package_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
    storage: Storage = Depends(get_storage),
):
    """The 006 play payload, from the pinned package version."""
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    _refuse_if_voided(enrollment)
    package = _get_pinned_package_or_404(db, enrollment, package_id)
    progress = enrollments.progress(db, enrollment)
    furthest = next(
        (
            lesson["furthest_seconds"]
            for lesson in progress["lessons"]
            if lesson["package_id"] == package.id
        ),
        0,
    )
    return MyPlayLesson(
        lesson_id=package.lesson_id,
        title=package.title,
        video_url=storage.url_for(package.video_key, VIDEO_URL_SECONDS),
        duration_seconds=package.duration_seconds,
        blocks=[PlayBlock(**block) for block in (package.blocks or [])],
        questions=[
            PlayQuestion(
                question_key=q.question_key,
                after_block=q.after_block,
                stem=q.stem,
                choices=[
                    PlayChoice(choice_key=c.choice_key, text=c.text)
                    for c in q.choices
                ],
            )
            for q in questions_service.for_package(db, package.id)
            if q.kind == "review"
        ],
        furthest_seconds=furthest,
    )


@router.post(
    "/enrollments/{enrollment_id}/lessons/{package_id}/review/{question_key}",
    response_model=ReviewResult,
    responses={422: {"model": ValidationErrors}},
)
def grade_review(
    enrollment_id: int,
    package_id: int,
    question_key: str,
    answer: ReviewAnswer,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    """006's grading, plus persistence: the verdict is recorded as the
    5.01.2 engagement record, and a re-answer updates it. The response is
    exactly what 006 returned."""
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    _refuse_if_voided(enrollment)
    package = _get_pinned_package_or_404(db, enrollment, package_id)
    question = questions_service.get_question(db, package.id, question_key)
    if question is None or question.kind != "review":
        raise HTTPException(status_code=404, detail="Review question not found")
    chosen = next(
        (c for c in question.choices if c.choice_key == answer.choice_key), None
    )
    if chosen is None:
        return JSONResponse(
            status_code=422,
            content={
                "errors": [
                    f'choice_key "{answer.choice_key}" is not a choice of '
                    f"question {question_key}"
                ]
            },
        )
    enrollments.record_review_answer(db, enrollment, question, chosen)
    correct_choice = next(c for c in question.choices if c.is_correct)
    return ReviewResult(
        correct=chosen.is_correct,
        feedback=question.feedback,
        correct_choice_key=correct_choice.choice_key,
    )


@router.put(
    "/enrollments/{enrollment_id}/lessons/{package_id}/progress",
    response_model=ProgressOut,
)
def put_progress(
    enrollment_id: int,
    package_id: int,
    payload: ProgressUpdate,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    _refuse_if_voided(enrollment)
    package = _get_pinned_package_or_404(db, enrollment, package_id)
    row = enrollments.record_progress(
        db, enrollment, package, payload.furthest_seconds
    )
    return ProgressOut(
        package_id=package.id, furthest_seconds=row.furthest_seconds
    )


@router.get(
    "/enrollments/{enrollment_id}/assessment", response_model=MyAssessmentInfo
)
def get_assessment(
    enrollment_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    progress = enrollments.progress(db, enrollment)
    open_attempt = assessment.open_attempt_for_enrollment(db, enrollment)
    questions = assessment.questions_for_enrollment(db, enrollment)
    retakes = enrollments.retakes_remaining(db, enrollment)
    return MyAssessmentInfo(
        course_code=enrollment.course.course_code,
        title=enrollment.course.title,
        question_count=len(questions),
        passing_pct=str(PASSING_PCT),
        retakes_allowed=RETAKES_ALLOWED,
        retakes_remaining=retakes,
        open_attempt_id=open_attempt.id if open_attempt else None,
        available=progress["assessment_available"] and retakes > 0,
        unavailable_reasons=_unavailable_reasons(db, enrollment, progress),
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


def _get_attempt_or_404(
    db: Session, enrollment: Enrollment, attempt_id: int
) -> Attempt:
    attempt = db.get(Attempt, attempt_id)
    if attempt is None or attempt.enrollment_id != enrollment.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt


@router.post(
    "/enrollments/{enrollment_id}/assessment/attempts",
    response_model=AttemptStarted,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def start_attempt(
    enrollment_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    try:
        attempt = assessment.start_for_enrollment(db, enrollment)
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
    "/enrollments/{enrollment_id}/assessment/attempts/{attempt_id}/answers",
    response_model=AnswersSaved,
    responses={422: {"model": ValidationErrors}},
)
def save_answers(
    enrollment_id: int,
    attempt_id: int,
    payload: AnswersRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    attempt = _get_attempt_or_404(db, enrollment, attempt_id)
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
    "/enrollments/{enrollment_id}/assessment/attempts/{attempt_id}/submit",
    responses={422: {"model": ValidationErrors}},
)
def submit_attempt(
    enrollment_id: int,
    attempt_id: int,
    payload: AnswersRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    attempt = _get_attempt_or_404(db, enrollment, attempt_id)
    try:
        attempt = assessment.submit(db, attempt, payload.answers)
    except CreditStale as stale:
        return JSONResponse(status_code=409, content={"errors": stale.errors})
    except AssessmentRuleViolation as violation:
        return _violation_response(violation)
    return assessment.result(attempt)


@router.get("/enrollments/{enrollment_id}/assessment/attempts/{attempt_id}")
def get_attempt(
    enrollment_id: int,
    attempt_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    enrollment = _get_enrollment_or_404(db, account, enrollment_id)
    attempt = _get_attempt_or_404(db, enrollment, attempt_id)
    return assessment.result(attempt)


def _get_completion_or_404(db: Session, account: Account, completion_id: int):
    completion = completions.get(db, completion_id)
    if completion is None or completion.enrollment.account_id != account.id:
        raise HTTPException(status_code=404, detail="Completion not found")
    return completion


@router.get(
    "/completions/{completion_id}/evaluation", response_model=MyEvaluationInfo
)
def get_evaluation(
    completion_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    """Whether the 4.04.1 prompt should appear, and the exact wording to
    ask with. Only the four applicable elements are served; item 5
    (instructors) is never asked of a self study participant."""
    completion = _get_completion_or_404(db, account, completion_id)
    return MyEvaluationInfo(
        due=evaluations.solicit(db, completion),
        submitted=evaluations.get_for_completion(db, completion) is not None,
        scale_min=SCALE_MIN,
        scale_max=SCALE_MAX,
        prompts=[
            EvaluationPrompt(key=element, text=PROMPTS[element])
            for element in RATED_ELEMENTS
        ],
    )


@router.post(
    "/completions/{completion_id}/evaluation",
    response_model=MyEvaluationInfo,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def submit_evaluation(
    completion_id: int,
    payload: EvaluationSubmit,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    completion = _get_completion_or_404(db, account, completion_id)
    try:
        evaluations.submit(db, completion, payload.ratings, payload.comments)
    except EvaluationRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    return MyEvaluationInfo(
        due=False,
        submitted=True,
        scale_min=SCALE_MIN,
        scale_max=SCALE_MAX,
        prompts=[
            EvaluationPrompt(key=element, text=PROMPTS[element])
            for element in RATED_ELEMENTS
        ],
    )


@router.get("/completions/{completion_id}/certificate.pdf")
def download_certificate(
    completion_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
    storage: Storage = Depends(get_storage),
):
    """Streams the stored certificate, rendering it first if this is the
    first download and the sponsor's issuance fields allow. While they do
    not, 409: the completion stands, the certificate is pending."""
    completion = completions.get(db, completion_id)
    if completion is None or completion.enrollment.account_id != account.id:
        raise HTTPException(status_code=404, detail="Completion not found")
    try:
        completions.ensure_rendered(db, storage, completion)
    except IssuanceBlocked:
        return JSONResponse(
            status_code=409,
            content={
                "errors": [
                    "Your completion is recorded; your certificate will be "
                    "issued shortly."
                ]
            },
        )
    with storage.open(completion.certificate_key) as pdf:
        content = pdf.read()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                "inline; filename="
                f'"certificate-{completion.certificate_number}.pdf"'
            )
        },
    )
