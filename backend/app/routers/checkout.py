"""Checkout (018): a verified participant buys a published course.

Both routes sit behind `require_site_open_or_session` like the catalog —
404 anonymously while the site is coming_soon — and behind the
participant role. The POST returns Stripe's hosted page URL; the status
GET is what the success page polls while it waits for the webhook (the
sole creator of enrollments) to land.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role, require_site_open_or_session
from app.db import get_db
from app.models.account import Account
from app.schemas.package import ValidationErrors
from app.schemas.payment import (
    CheckoutRequest,
    CheckoutStarted,
    CheckoutStatusOut,
)
from app.services import courses, payments, stripe_gateway
from app.services import enrollments as enrollments_service
from app.services import sponsor as sponsor_service
from app.services.payments import PaymentRuleViolation

router = APIRouter(
    prefix="/checkout",
    dependencies=[Depends(require_site_open_or_session)],
)

participant = require_role("participant")


@router.post(
    "",
    response_model=CheckoutStarted,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def start_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    course = courses.get_course(db, payload.course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    try:
        payment = payments.start_checkout(db, account, course)
    except PaymentRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    except stripe_gateway.StripeGatewayError:
        # The detail stays in the server log; a participant cannot act
        # on a Stripe error string.
        return JSONResponse(
            status_code=502,
            content={
                "errors": [
                    "The payment provider could not be reached. Nothing "
                    "was charged; try again in a moment."
                ]
            },
        )
    return CheckoutStarted(
        payment_id=payment.id, checkout_url=payment.checkout_url
    )


@router.get("/{session_id}/status", response_model=CheckoutStatusOut)
def checkout_status(
    session_id: str,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    """Owner-only: whether a payment exists is nobody else's business,
    so a foreign session id is a 404, not a 403."""
    payment = payments.get_by_session_id(db, session_id)
    if payment is None or payment.account_id != account.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    enrollment = payments.enrollment_created_by(db, payment)
    return CheckoutStatusOut(
        status=payment.status,
        enrollment_id=enrollment.id if enrollment else None,
        course_code=payment.course.course_code,
        course_title=payment.course.title,
        support_email=sponsor_service.get_profile(db).contact_email,
    )
