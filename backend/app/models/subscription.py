from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.subscription import (
    SUBSCRIPTION_INVOICE_STATUSES,
    SUBSCRIPTION_STATUSES,
)
from app.db import Base


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Subscription(Base):
    """One Stripe Billing subscription for one account (029): the
    entitlement's paper trail. Stripe owns the renewal schedule and the
    card; this row records what Stripe last reported.

    Financial record, never deleted — not subject to `RETENTION_YEARS`,
    which is a floor for CPE records; these outlive it, like `payments`.
    A lapse deletes nothing: "all my data is still there" rests on this
    row and its invoices staying put.

    Whether the account is *currently* subscribed is derived
    (`services.subscriptions.current`: status `active` and now before
    `current_period_end`), never stored as a flag. `status`, both period
    ends, `cancel_at_period_end`, and `canceled_at` are copied from
    Stripe's subscription object as the webhook delivers it — never
    inferred from an invoice, a date, or a key prefix. `credit_applied_cents`
    is the discount Stripe reported on the first invoice, not the number
    superCPE computed when it minted the coupon. `livemode` follows 026's
    rule: Stripe's word, recorded and displayed, never branched on.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    # Null until Checkout completes; the completion event sets it.
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    # The hosted Checkout page URL, kept so a repeat subscribe inside the
    # session lifetime returns the live session instead of minting another
    # (018's rule for payments).
    checkout_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # As Stripe reports it. Written `incomplete` before the redirect URL
    # is returned; every later value is copied from a Stripe object.
    status: Mapped[str] = mapped_column(String, nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The discount Stripe reported on the completed Checkout Session
    # (`total_details.amount_discount`); 0 until the webhook says so.
    credit_applied_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    livemode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    account = relationship("Account")
    invoices: Mapped[list["SubscriptionInvoice"]] = relationship(
        back_populates="subscription",
        order_by="SubscriptionInvoice.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_in_list(SUBSCRIPTION_STATUSES)})",
            name="ck_subscriptions_status",
        ),
        CheckConstraint(
            "credit_applied_cents >= 0",
            name="ck_subscriptions_credit_non_negative",
        ),
    )


class SubscriptionInvoice(Base):
    """One Stripe invoice on one subscription (029): the renewal paper
    trail, one row per invoice as `invoice.paid` / `invoice.payment_failed`
    deliver it. `refunded` is superCPE's own mark from `charge.refunded`
    (Stripe leaves the invoice `paid`); the mark is the whole effect —
    nothing voids, nothing cancels, the admin decides (018's rule).

    Financial record, never deleted; outlives `RETENTION_YEARS`. Amount,
    currency, and period are stored as Stripe reported them on the
    invoice, never re-derived from the Price or the constant.
    """

    __tablename__ = "subscription_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    stripe_invoice_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True
    )
    # The payment behind the invoice, as Stripe reported it: what a later
    # `charge.refunded` event carries, and therefore how the refund finds
    # this row. Null on an invoice that has not been paid.
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    amount_paid_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    livemode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subscription: Mapped[Subscription] = relationship(back_populates="invoices")

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_in_list(SUBSCRIPTION_INVOICE_STATUSES)})",
            name="ck_subscription_invoices_status",
        ),
        CheckConstraint(
            "amount_paid_cents >= 0",
            name="ck_subscription_invoices_amount_non_negative",
        ),
    )
