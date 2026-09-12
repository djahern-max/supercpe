from datetime import datetime

from pydantic import BaseModel

from app.schemas.course import PolicyLink


class SubscribeOfferOut(BaseModel):
    """The /subscribe page's 8.01 disclosure about the *subscription*:
    price (from the constant), term, the viewer's purchase credit, and
    links to the registration and refund policies. Names no course."""

    price_cents: int
    currency: str
    period_days: int
    # 0 for a visitor or an account with nothing to credit.
    credit_cents: int
    pay_today_cents: int
    # Whether the viewer already holds a current subscription.
    subscribed: bool
    registration_policy: PolicyLink | None
    refund_policy: PolicyLink | None


class SubscribeStarted(BaseModel):
    subscription_id: int
    checkout_url: str


class SubscribeStatusOut(BaseModel):
    """What the success page polls: Stripe's status as last reported,
    whether that makes the subscription current, and the credit Stripe
    reported on the first invoice."""

    status: str
    current: bool
    credit_applied_cents: int
    current_period_end: datetime | None
    support_email: str


class MySubscriptionOut(BaseModel):
    """The /account Subscription section. `state` is derived for the
    page: none | current | cancels_at_period_end | past_due | lapsed."""

    state: str
    status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    credit_applied_cents: int
    # Whether "Manage subscription" (the Stripe Customer Portal) applies.
    manageable: bool


class PortalOut(BaseModel):
    url: str


class AdminSubscriptionInvoiceOut(BaseModel):
    id: int
    stripe_invoice_id: str
    stripe_payment_intent_id: str | None
    amount_paid_cents: int
    currency: str
    status: str
    period_start: datetime | None
    period_end: datetime | None
    livemode: bool | None
    created_at: datetime


class AdminSubscriptionEnrollmentOut(BaseModel):
    """An active enrollment started under a refunded subscription: the
    row the existing void action (018) answers."""

    enrollment_id: int
    course_code: str
    expires_at: datetime


class AdminSubscriptionOut(BaseModel):
    id: int
    email: str
    display_name: str
    stripe_subscription_id: str | None
    stripe_customer_id: str | None
    status: str
    current: bool
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    credit_applied_cents: int
    livemode: bool | None
    created_at: datetime
    updated_at: datetime
    invoices: list[AdminSubscriptionInvoiceOut]
    # The two loud flags: a refunded invoice on a subscription that is
    # still current, and on an account that still holds active
    # subscription-sourced enrollments (listed, each voidable).
    refunded_with_current_subscription: bool
    refunded_with_active_enrollments: bool
    active_enrollments: list[AdminSubscriptionEnrollmentOut]
