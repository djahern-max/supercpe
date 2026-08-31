"""Admin payments view and the guarded void action (018).

The view is the paper trail: every checkout attempt that reached Stripe,
with the loud `refunded_with_active_enrollment` flag — a refund never
unwinds access automatically, so that flag is the queue of refund-policy
decisions awaiting an admin. Voiding is the "access ends" answer,
deactivate-never-delete per 010.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.models.enrollment import Enrollment
from app.models.payment import Payment
from app.schemas.package import ValidationErrors
from app.schemas.payment import AdminPaymentOut, VoidedEnrollmentOut
from app.services import enrollments as enrollments_service
from app.services import payments as payments_service
from app.services.enrollments import EnrollmentRuleViolation

router = APIRouter(
    prefix="/admin", dependencies=[Depends(require_role("admin"))]
)


def _payment_out(db: Session, payment: Payment) -> AdminPaymentOut:
    enrollment = payments_service.enrollment_created_by(db, payment)
    enrollment_status = (
        enrollments_service.status(enrollment) if enrollment else None
    )
    return AdminPaymentOut(
        id=payment.id,
        email=payment.account.email,
        display_name=payment.account.display_name,
        course_code=payment.course.course_code,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        status=payment.status,
        stripe_checkout_session_id=payment.stripe_checkout_session_id,
        stripe_payment_intent_id=payment.stripe_payment_intent_id,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        enrollment_id=enrollment.id if enrollment else None,
        enrollment_status=enrollment_status,
        refunded_with_active_enrollment=(
            payment.status == "refunded" and enrollment_status == "active"
        ),
    )


@router.get("/payments", response_model=list[AdminPaymentOut])
def list_payments(db: Session = Depends(get_db)):
    return [
        _payment_out(db, payment)
        for payment in payments_service.list_payments(db)
    ]


@router.post(
    "/enrollments/{enrollment_id}/void",
    response_model=VoidedEnrollmentOut,
    responses={422: {"model": ValidationErrors}},
)
def void_enrollment(
    enrollment_id: int,
    db: Session = Depends(get_db),
    admin: Account = Depends(require_role("admin")),
):
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    try:
        enrollments_service.void(db, enrollment, admin)
    except EnrollmentRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    return VoidedEnrollmentOut(
        enrollment_id=enrollment.id,
        status=enrollments_service.status(enrollment),
        voided_at=enrollment.voided_at,
        voided_by_email=admin.email,
    )
