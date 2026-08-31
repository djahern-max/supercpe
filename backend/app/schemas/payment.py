from datetime import datetime

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    course_code: str = Field(min_length=1)


class CheckoutStarted(BaseModel):
    """Where to send the participant: Stripe's hosted page. Card data
    never transits superCPE."""

    payment_id: int
    checkout_url: str


class CheckoutStatusOut(BaseModel):
    """What the success page polls: the payment's status and, once the
    webhook lands, the enrollment to link to. `support_email` is the
    sponsor's contact address for the "taking longer than usual" state."""

    status: str
    enrollment_id: int | None
    course_code: str
    course_title: str
    support_email: str


class AdminPaymentOut(BaseModel):
    """One row of the money's paper trail as /admin/payments lists it.
    The Stripe ids are for dashboard links; `refunded_with_active_enrollment`
    is the loud flag that a refund's access question awaits an admin."""

    id: int
    email: str
    display_name: str
    course_code: str
    amount_cents: int
    currency: str
    status: str
    stripe_checkout_session_id: str
    stripe_payment_intent_id: str | None
    created_at: datetime
    updated_at: datetime
    # Derived: the enrollment this payment created, when one exists.
    enrollment_id: int | None
    enrollment_status: str | None
    refunded_with_active_enrollment: bool


class VoidedEnrollmentOut(BaseModel):
    enrollment_id: int
    status: str
    voided_at: datetime
    voided_by_email: str
