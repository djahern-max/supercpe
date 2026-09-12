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

from app.db import Base

PAYMENT_STATUSES = ("pending", "paid", "refunded", "expired")


class Payment(Base):
    """One checkout attempt that reached Stripe: the money's paper trail.

    Financial records, never deleted — not subject to `RETENTION_YEARS`,
    which is a floor for CPE records; these outlive it (tax and dispute
    trails have their own clocks). `amount_cents` and `currency` are
    stored as Stripe reported them on the session and re-stamped from the
    completion event, never re-derived from the course: the course's
    price can change, what was charged cannot.

    The enrollment a paid row created is derived (the account's
    enrollment on the course from on or after this row's creation), not
    stored — the webhook creates it via 010's one constructor and 010's
    one-active-per-(account, course) invariant makes the lookup exact.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    stripe_checkout_session_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True
    )
    # Null until Stripe reports it (usually on the completed event); the
    # refund event carries it, so `charge.refunded` finds the row by it.
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    # The hosted Checkout page URL, kept so a repeat checkout inside the
    # session lifetime returns the live session instead of minting another.
    checkout_url: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    # pending -> paid -> refunded, plus expired for abandoned sessions.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    # 026: Stripe's own `livemode` on the Checkout Session, stored as
    # reported when the session is created and re-stamped from the
    # completion event — never inferred from the key prefix, the same
    # rule as amount and currency. A test transaction is then
    # permanently and honestly distinguishable in the record without
    # anything being deleted, which is what 9.02's never-delete posture
    # requires of us. Recorded and displayed, never branched on. Null
    # only on rows that predate the column (none exist in production).
    livemode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 029: set when this course payment's amount was applied, dollar for
    # dollar, as credit on a subscription's first invoice — so it is
    # never credited twice. A stored fact about a financial event (the
    # discount Stripe reported on a specific invoice), not derived state;
    # written only by the webhook that confirmed the discounted invoice,
    # never at session creation, so an abandoned session burns nothing.
    credited_to_subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=True
    )
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
    course = relationship("Course")
    credited_to_subscription = relationship("Subscription")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'paid', 'refunded', 'expired')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "amount_cents > 0", name="ck_payments_amount_positive"
        ),
    )


class StripeWebhookEvent(Base):
    """One processed Stripe webhook event, stored for idempotency: a
    replayed event id answers 200 and does nothing. Only events that
    changed something are recorded; ignored event types are logged by
    name and not stored (replaying them is already a no-op)."""

    __tablename__ = "stripe_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
