"""Admin enrollment and completion views: enroll a participant by email,
list a course's enrollments and completions, render and download
certificates."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.models.course import Course
from app.models.enrollment import Completion, Enrollment
from app.schemas.enrollment import (
    AdminCompletionOut,
    AdminEnrollmentOut,
    EnrollRequest,
)
from app.schemas.package import ValidationErrors
from app.services import completions, enrollments, retention
from app.services import auth as auth_service
from app.services import courses
from app.services.completions import IssuanceBlocked
from app.services.enrollments import EnrollmentRuleViolation
from app.storage import Storage, get_storage

router = APIRouter(
    prefix="/admin", dependencies=[Depends(require_role("admin"))]
)


def _get_course_or_404(db: Session, course_code: str) -> Course:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _enrollment_out(db: Session, enrollment: Enrollment) -> AdminEnrollmentOut:
    progress = enrollments.progress(db, enrollment)
    return AdminEnrollmentOut(
        id=enrollment.id,
        email=enrollment.account.email,
        display_name=enrollment.account.display_name,
        status=enrollments.status(enrollment),
        source=enrollment.source,
        enrolled_at=enrollment.enrolled_at,
        expires_at=enrollment.expires_at,
        package_versions=enrollment.package_versions,
        lessons_total=len(progress["lessons"]),
        lessons_watched=sum(
            1
            for lesson in progress["lessons"]
            if lesson["furthest_seconds"] >= lesson["duration_seconds"] - 1
        ),
        review_answered=progress["review_answered"],
        review_total=progress["review_total"],
        failed_attempts=enrollments.failed_attempts(db, enrollment),
        has_completion=enrollment.completion is not None,
    )


def _completion_out(db: Session, completion: Completion) -> AdminCompletionOut:
    return AdminCompletionOut(
        id=completion.id,
        enrollment_id=completion.enrollment_id,
        email=completion.enrollment.account.email,
        participant_name=completion.enrollment.account.display_name,
        completed_at=completion.completed_at,
        credit_awarded=str(completion.credit_awarded),
        field_of_study=completion.field_of_study,
        certificate_number=completion.certificate_number,
        certificate_rendered_at=completion.certificate_rendered_at,
        certificate_ready=completions.certificate_ready(db, completion),
        overdue=completion in completions.overdue(db),
        retain_until=retention.retain_until(completion.completed_at),
    )


@router.post(
    "/courses/{course_code}/enrollments",
    response_model=AdminEnrollmentOut,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def enroll_participant(
    course_code: str,
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    admin: Account = Depends(require_role("admin")),
):
    course = _get_course_or_404(db, course_code)
    account = auth_service.get_account_by_email(
        db, payload.email.strip().lower()
    )
    if account is None:
        return JSONResponse(
            status_code=422,
            content={
                "errors": [
                    f"No account exists for {payload.email}; create the "
                    "participant account first."
                ]
            },
        )
    try:
        enrollment = enrollments.enroll(
            db, account, course, created_by=admin, source="admin"
        )
    except EnrollmentRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    return _enrollment_out(db, enrollment)


@router.get(
    "/courses/{course_code}/enrollments",
    response_model=list[AdminEnrollmentOut],
)
def list_enrollments(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    return [
        _enrollment_out(db, enrollment)
        for enrollment in enrollments.list_for_course(db, course)
    ]


@router.get(
    "/courses/{course_code}/completions",
    response_model=list[AdminCompletionOut],
)
def list_completions(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    return [
        _completion_out(db, enrollment.completion)
        for enrollment in enrollments.list_for_course(db, course)
        if enrollment.completion is not None
    ]


def _get_completion_or_404(db: Session, completion_id: int) -> Completion:
    completion = completions.get(db, completion_id)
    if completion is None:
        raise HTTPException(status_code=404, detail="Completion not found")
    return completion


@router.post(
    "/completions/{completion_id}/render",
    response_model=AdminCompletionOut,
    responses={422: {"model": ValidationErrors}},
)
def render_certificate(
    completion_id: int,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    completion = _get_completion_or_404(db, completion_id)
    try:
        completions.ensure_rendered(db, storage, completion)
    except IssuanceBlocked as blocked:
        return JSONResponse(status_code=422, content={"errors": blocked.errors})
    return _completion_out(db, completion)


@router.get("/completions/{completion_id}/certificate.pdf")
def download_certificate(
    completion_id: int,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    completion = _get_completion_or_404(db, completion_id)
    try:
        completions.ensure_rendered(db, storage, completion)
    except IssuanceBlocked as blocked:
        return JSONResponse(status_code=422, content={"errors": blocked.errors})
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
