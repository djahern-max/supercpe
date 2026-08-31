from datetime import datetime

from sqlalchemy import (
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
