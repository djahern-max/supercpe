"""Checkout and the money's paper trail (018).

Stripe holds the card; superCPE holds one `payments` row per checkout
attempt that reached Stripe. The webhook is the sole creator of
enrollments: a browser landing on the success URL proves nothing, so
`handle_event` — fed only signature-verified events — is where a payment
becomes an enrollment, via 010's one constructor. Rule violations raise
`PaymentRuleViolation` for the router to wrap in a 422
`{"errors": [...]}`, the same shape as everywhere else.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.payments import (
    CHECKOUT_SESSION_LIFETIME_HOURS,
    PAYMENT_CURRENCY,
)
from app.models.account import Account
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.payment import Payment, StripeWebhookEvent
from app.services import enrollments as enrollments_service
from app.services import stripe_gateway
from app.services.enrollments import EnrollmentRuleViolation

logger = logging.getLogger(__name__)


class PaymentRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_enrollment(
    db: Session, account: Account, course: Course
) -> Enrollment | None:
    return next(
        (
            e
            for e in db.scalars(
                select(Enrollment).where(
                    Enrollment.account_id == account.id,
                    Enrollment.course_id == course.id,
                )
            )
            if enrollments_service.status(e) == "active"
        ),
        None,
    )


def _live_pending_payment(
    db: Session, account: Account, course: Course
) -> Payment | None:
    """A `pending` payment younger than the Checkout Session lifetime: a
    page the participant can still pay on, returned instead of minting a
    second session for the same purchase."""
    cutoff = _now() - timedelta(hours=CHECKOUT_SESSION_LIFETIME_HOURS)
    return db.scalar(
        select(Payment)
        .where(
            Payment.account_id == account.id,
            Payment.course_id == course.id,
            Payment.status == "pending",
            Payment.created_at > cutoff,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(1)
    )


def start_checkout(db: Session, account: Account, course: Course) -> Payment:
    """The pending payment row for a new (or still-live) Checkout
    Session; `checkout_url` is where to send the participant."""
    errors = []
    if course.status != "published":
        errors.append(
            f"course {course.course_code} is {course.status}; only "
            "published courses can be purchased"
        )
    # 017's verification gate already refuses login while unverified;
    # kept as belt and braces because money is about to move.
    if account.email_verified_at is None:
        errors.append(
            f"{account.email} is not verified; verify your email address "
            "before purchasing"
        )
    if course.price_cents is None or course.price_cents <= 0:
        # Unreachable through the publish gate; defense in depth.
        errors.append(
            f"course {course.course_code} has no price and cannot be "
            "purchased"
        )
    existing = _active_enrollment(db, account, course)
    if existing is not None:
        errors.append(
            f"you already hold an active enrollment on "
            f"{course.course_code}, expiring "
            f"{existing.expires_at.date().isoformat()}; it can be "
            "purchased again after it expires"
        )
    if errors:
        raise PaymentRuleViolation(errors)

    live = _live_pending_payment(db, account, course)
    if live is not None:
        return live

    origin = settings.cors_origins_list[0]
    payment = Payment(
        account_id=account.id,
        course_id=course.id,
        # Placeholders overwritten below before the commit; the row only
        # ever exists with the session Stripe actually created.
        stripe_checkout_session_id="",
        checkout_url="",
        amount_cents=course.price_cents,
        currency=PAYMENT_CURRENCY,
        status="pending",
    )
    db.add(payment)
    db.flush()  # the row id rides in the session metadata
    try:
        session = stripe_gateway.create_checkout_session(
            course_title=course.title,
            course_code=course.course_code,
            price_cents=course.price_cents,
            currency=PAYMENT_CURRENCY,
            account_id=account.id,
            payment_id=payment.id,
            customer_email=account.email,
            # Stripe substitutes the literal {CHECKOUT_SESSION_ID}.
            success_url=(
                f"{origin}/purchase/success"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{origin}/courses/{course.course_code}",
        )
    except stripe_gateway.StripeGatewayError:
        db.rollback()
        raise
    payment.stripe_checkout_session_id = session.id
    payment.stripe_payment_intent_id = session.payment_intent_id
    payment.checkout_url = session.url
    # As Stripe reported them, not as superCPE asked.
    payment.amount_cents = session.amount_cents
    payment.currency = session.currency
    db.commit()
    return payment


def get_by_session_id(db: Session, session_id: str) -> Payment | None:
    return db.scalar(
        select(Payment).where(
            Payment.stripe_checkout_session_id == session_id
        )
    )


def enrollment_created_by(db: Session, payment: Payment) -> Enrollment | None:
    """The enrollment a paid row created, derived, never stored: this
    account's newest enrollment on this course from on or after the
    payment was started (the webhook creates it moments after)."""
    if payment.status not in ("paid", "refunded"):
        return None
    return db.scalar(
        select(Enrollment)
        .where(
            Enrollment.account_id == payment.account_id,
            Enrollment.course_id == payment.course_id,
            Enrollment.source == "purchase",
            Enrollment.enrolled_at >= payment.created_at,
        )
        .order_by(Enrollment.enrolled_at.desc(), Enrollment.id.desc())
        .limit(1)
    )


def list_payments(db: Session) -> list[Payment]:
    """Newest first, for the admin payments view."""
    return list(
        db.scalars(
            select(Payment).order_by(
                Payment.created_at.desc(), Payment.id.desc()
            )
        )
    )


def _already_processed(db: Session, event_id: str) -> bool:
    return (
        db.scalar(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.stripe_event_id == event_id
            )
        )
        is not None
    )


def _record_event(db: Session, event: dict) -> None:
    db.add(
        StripeWebhookEvent(
            stripe_event_id=event["id"], event_type=event["type"]
        )
    )


def handle_event(db: Session, event: dict) -> None:
    """Applies one signature-verified Stripe event. Never raises: Stripe
    retries non-2xx responses forever, so every failure mode here is a
    loud log line and a quiet 200. Idempotent by event id — a replay
    does nothing."""
    event_id = event["id"]
    event_type = event["type"]
    if _already_processed(db, event_id):
        logger.info("stripe event %s (%s) replayed; ignoring", event_id, event_type)
        return

    if event_type == "checkout.session.completed":
        _handle_completed(db, event)
    elif event_type == "checkout.session.expired":
        _handle_expired(db, event)
    elif event_type == "charge.refunded":
        _handle_refunded(db, event)
    else:
        # Unhandled on purpose; named so the log shows what Stripe sends.
        logger.info(
            "stripe event %s has unhandled type %s; ignoring",
            event_id,
            event_type,
        )


def _payment_from_metadata(db: Session, event: dict) -> Payment | None:
    metadata = event["data"]["object"].get("metadata") or {}
    payment_id = metadata.get("payment_id")
    if payment_id is None:
        return None
    return db.get(Payment, int(payment_id))


def _handle_completed(db: Session, event: dict) -> None:
    """Mark the payment paid and create the enrollment via 010, in one
    transaction (enroll's commit carries all of it)."""
    session_obj = event["data"]["object"]
    payment = _payment_from_metadata(db, event)
    if payment is None:
        # Metadata pointing at a row a rollback ate, or no metadata at
        # all. Loud, and 200: a 500 would make Stripe retry forever.
        logger.error(
            "stripe event %s: completed session %s names no payment row; "
            "investigate in the Stripe dashboard",
            event["id"],
            session_obj.get("id"),
        )
        _record_event(db, event)
        db.commit()
        return
    if payment.status == "paid":
        # Idempotency belt and braces: a duplicate completion under a
        # fresh event id.
        logger.info(
            "stripe event %s: payment %s already paid; ignoring",
            event["id"],
            payment.id,
        )
        _record_event(db, event)
        db.commit()
        return
    payment.status = "paid"
    if session_obj.get("payment_intent"):
        payment.stripe_payment_intent_id = session_obj["payment_intent"]
    # As Stripe reported them on the completed session.
    if session_obj.get("amount_total"):
        payment.amount_cents = session_obj["amount_total"]
    if session_obj.get("currency"):
        payment.currency = session_obj["currency"]
    _record_event(db, event)
    try:
        enrollments_service.enroll(
            db,
            payment.account,
            payment.course,
            created_by=None,
            source="purchase",
        )
    except EnrollmentRuleViolation as violation:
        # The money moved; the payment is paid either way. The refusal
        # (course unpublished since checkout, an enrollment raced in) is
        # an admin's problem, loudly.
        logger.error(
            "stripe event %s: payment %s is paid but 010 refused the "
            "enrollment: %s",
            event["id"],
            payment.id,
            "; ".join(violation.errors),
        )
        db.commit()


def _handle_expired(db: Session, event: dict) -> None:
    payment = _payment_from_metadata(db, event)
    if payment is None:
        logger.error(
            "stripe event %s: expired session names no payment row",
            event["id"],
        )
    elif payment.status == "pending":
        payment.status = "expired"
    _record_event(db, event)
    db.commit()


def _handle_refunded(db: Session, event: dict) -> None:
    """Mark the payment refunded and stop. Whether a refund unwinds
    access is the published refund policy's question and an admin's
    answer (the guarded void action) — never this handler's."""
    charge = event["data"]["object"]
    intent_id = charge.get("payment_intent")
    payment = (
        db.scalar(
            select(Payment).where(
                Payment.stripe_payment_intent_id == intent_id
            )
        )
        if intent_id
        else None
    )
    if payment is None:
        logger.error(
            "stripe event %s: refund for unknown payment intent %s",
            event["id"],
            intent_id,
        )
    else:
        payment.status = "refunded"
    _record_event(db, event)
    db.commit()
