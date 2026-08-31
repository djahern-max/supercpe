"""017: self-registration, verification, resend, and the admin test email.

The public routes sit behind `require_site_open_or_session` like the
catalog: while the site is coming_soon they 404 anonymously (nothing is
added to the 015 walk's allowlist), and they are public at open. All
three are rate limited by Caddy mirroring the login rule.

The registration and resend responses are byte-identical for every
well-formed submission — the shared CHECK_YOUR_EMAIL constant — and a
bad verification token gets one failure whatever was wrong with it.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role, require_site_open_or_session
from app.db import get_db
from app.models.account import Account
from app.routers.auth import require_json
from app.schemas.package import ValidationErrors
from app.schemas.register import (
    RegisteredOut,
    RegisterRequest,
    ResendRequest,
    TestEmailOut,
    VerifiedOut,
    VerifyRequest,
)
from app.services import email as email_service
from app.services import registration as registration_service
from app.services.registration import RegistrationRuleViolation

router = APIRouter(
    dependencies=[
        Depends(require_site_open_or_session),
        Depends(require_json),
    ]
)
admin_router = APIRouter(
    prefix="/admin/email", dependencies=[Depends(require_role("admin"))]
)

CHECKED = RegisteredOut(message=registration_service.CHECK_YOUR_EMAIL)


@router.post(
    "/register",
    response_model=RegisteredOut,
    responses={422: {"model": ValidationErrors}},
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        registration_service.register(
            db, payload.name, payload.email, payload.password, payload.state
        )
    except RegistrationRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return CHECKED


@router.post(
    "/resend-verification",
    response_model=RegisteredOut,
    responses={422: {"model": ValidationErrors}},
)
def resend_verification(
    payload: ResendRequest, db: Session = Depends(get_db)
):
    try:
        registration_service.resend(db, payload.email)
    except RegistrationRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return CHECKED


@router.post(
    "/verify",
    response_model=VerifiedOut,
    responses={422: {"model": ValidationErrors}},
)
def verify(payload: VerifyRequest, db: Session = Depends(get_db)):
    if not registration_service.verify(db, payload.token):
        return JSONResponse(
            status_code=422,
            content={"errors": [registration_service.VERIFY_FAILED]},
        )
    return VerifiedOut(message="Your email address is verified. You can sign in now.")


@admin_router.post(
    "/test",
    response_model=TestEmailOut,
    responses={502: {"model": ValidationErrors}},
)
def send_test_email(
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("admin")),
):
    """Proves the configured backend before the coming_soon -> open flip
    (the OPERATIONS.md runbook step). Sends to the requesting admin's own
    address — this is a config check, not a relay."""
    try:
        message = email_service.send(
            db,
            "test",
            account.email,
            "superCPE test email",
            (
                "This is the admin test email. If you are reading it, the "
                "configured email backend delivered it."
            ),
        )
    except Exception as exc:  # smtplib raises many types; name them all.
        return JSONResponse(
            status_code=502,
            content={"errors": [f"The email backend refused the send: {exc}"]},
        )
    return TestEmailOut(backend=message.backend, recipient=message.recipient)
