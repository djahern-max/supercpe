"""The annual subscription (029): entitlement, enrollment under it, the
subscribe flow with its purchase credit, and the Billing webhook handlers.

Stripe Billing owns the renewal schedule and the card; superCPE owns the
paper trail (`subscriptions`, `subscription_invoices`, the credit FK on
`payments`) and the entitlement. Every fact on those rows is copied from
a Stripe object as the webhook delivered it (or, once, as
`retrieve_subscription` returned it) — status, period, cancellation,
discount, `livemode` — never inferred from a date, a key prefix, or the
number superCPE asked for. Rule violations raise
`SubscriptionRuleViolation` for the router to wrap in a 422
`{"errors": [...]}`, the same shape as everywhere else.

Grace is decided here, once, as none: see `current`.
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
from app.constants.subscription import SUBSCRIPTION_PRICE_CENTS
from app.models.account import Account
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.payment import Payment
from app.models.subscription import Subscription, SubscriptionInvoice
from app.services import enrollments as enrollments_service
from app.services import stripe_gateway

logger = logging.getLogger(__name__)


class SubscriptionRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(value) -> datetime | None:
    """A Stripe unix timestamp as an aware datetime; None stays None."""
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _id_of(value) -> str | None:
    """Stripe references arrive as an id string or an expanded object."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("id")
    return str(value)


# --- entitlement -------------------------------------------------------------


def is_current(subscription: Subscription, now: datetime | None = None) -> bool:
    """Derived, never stored: Stripe's status is `active` and the period
    Stripe last reported has not ended."""
    now = now or _now()
    return (
        subscription.status == "active"
        and subscription.current_period_end is not None
        and subscription.current_period_end > now
    )


def current(db: Session, account: Account) -> Subscription | None:
    """The account's current subscription, or None: the newest row whose
    Stripe status is `active` and whose `current_period_end` is ahead of
    now, both as Stripe last reported them. No stored flag.

    This is the one place grace is decided, and it is decided as none:
    `past_due` is not current. Stripe retries the card on its own
    schedule and the participant sees "payment failed, update your card"
    on /account until `invoice.paid` lands and Stripe moves the
    subscription back to `active` (delivered as
    `customer.subscription.updated`). `incomplete`, `canceled`, `unpaid`,
    `trialing`, `paused`, and an `active` row whose period has ended are
    likewise not current."""
    now = _now()
    return db.scalar(
        select(Subscription)
        .where(
            Subscription.account_id == account.id,
            Subscription.status == "active",
            Subscription.current_period_end > now,
        )
        .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        .limit(1)
    )


def latest(db: Session, account: Account) -> Subscription | None:
    """The account's newest subscription row, current or not — what the
    /account section describes (renews on / cancels on / past due /
    lapsed / none)."""
    return db.scalar(
        select(Subscription)
        .where(Subscription.account_id == account.id)
        .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        .limit(1)
    )


def get_by_session_id(db: Session, session_id: str) -> Subscription | None:
    return db.scalar(
        select(Subscription).where(
            Subscription.stripe_checkout_session_id == session_id
        )
    )


def list_all(db: Session) -> list[Subscription]:
    """Newest first, for the admin view."""
    return list(
        db.scalars(
            select(Subscription).order_by(
                Subscription.created_at.desc(), Subscription.id.desc()
            )
        )
    )


# --- enrolling under it ------------------------------------------------------


def enroll_subscriber(db: Session, account: Account, course: Course) -> Enrollment:
    """A current subscriber's enrollment in a published course: no Stripe
    call, no payment row, 010's one constructor with
    `source="subscription"` and the standing one-year clock (9.02.2(3)
    — each enrollment carries its own expiration; the subscription's
    period is not an enrollment date). An expired prior enrollment is
    fine: this is the subscriber's renewal path, and it takes precedence
    over 028's route, which stays for non-subscribers. One 422 line per
    failed condition."""
    errors = []
    if current(db, account) is None:
        errors.append(
            "you do not have a current subscription; subscribe, or buy "
            f"{course.course_code} on its own"
        )
    if course.status != "published":
        errors.append(
            f"course {course.course_code} is {course.status}; only "
            "published courses can be enrolled in"
        )
    rows = enrollments_service.enrollments_for(db, account, course)
    for row in rows:
        row_status = enrollments_service.status(row)
        if row_status == "active":
            errors.append(
                f"you already hold an active enrollment on "
                f"{course.course_code}, expiring "
                f"{row.expires_at.date().isoformat()}"
            )
        elif row_status == "completed":
            errors.append(
                f"you have already completed {course.course_code}; there "
                "is nothing to enroll in again"
            )
    if errors:
        raise SubscriptionRuleViolation(errors)
    return enrollments_service.enroll(
        db, account, course, created_by=None, source="subscription"
    )


def subscription_enrollable(db: Session, enrollment: Enrollment) -> bool:
    """Whether this expired enrollment's course can be started again with
    a click because the participant is a current subscriber: the most
    recent enrollment on the course, expired, nothing active or completed,
    and a current subscription. The /my/courses card's "Enroll again
    (included)" — checked before 028's `renewable`, which stays for
    non-subscribers."""
    if enrollments_service.status(enrollment) != "expired":
        return False
    rows = enrollments_service.enrollments_for(
        db, enrollment.account, enrollment.course
    )
    if not rows or rows[0].id != enrollment.id:
        return False
    statuses = {enrollments_service.status(e) for e in rows}
    if "active" in statuses or "completed" in statuses:
        return False
    return current(db, enrollment.account) is not None


def active_subscription_enrollments(
    db: Session, account: Account
) -> list[Enrollment]:
    """The account's active enrollments started under a subscription —
    what the admin's refunded-with-active-enrollments flag lists, each
    with 018's void action beside it."""
    return [
        e
        for e in enrollments_service.list_for_account(db, account)
        if e.source == "subscription"
        and enrollments_service.status(e) == "active"
    ]


# --- subscribing and the credit ----------------------------------------------


def credit_payments(db: Session, account: Account) -> list[Payment]:
    """The course payments whose amounts stand as credit: `paid` (never
    refunded, never pending) and not yet credited to any subscription."""
    return list(
        db.scalars(
            select(Payment)
            .where(
                Payment.account_id == account.id,
                Payment.status == "paid",
                Payment.credited_to_subscription_id.is_(None),
            )
            .order_by(Payment.created_at, Payment.id)
        )
    )


def credit_cents(db: Session, account: Account) -> int:
    """Dollar-for-dollar credit against the first subscription payment,
    capped at the subscription price. Zero is a valid result."""
    total = sum(p.amount_cents for p in credit_payments(db, account))
    return min(total, SUBSCRIPTION_PRICE_CENTS)


def _live_incomplete(db: Session, account: Account) -> Subscription | None:
    """An `incomplete` row younger than the Checkout Session lifetime
    whose session has not completed: a page the participant can still
    pay on, returned instead of minting a second one (018's rule)."""
    cutoff = _now() - timedelta(hours=CHECKOUT_SESSION_LIFETIME_HOURS)
    return db.scalar(
        select(Subscription)
        .where(
            Subscription.account_id == account.id,
            Subscription.status == "incomplete",
            Subscription.stripe_subscription_id.is_(None),
            Subscription.checkout_url.is_not(None),
            Subscription.created_at > cutoff,
        )
        .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        .limit(1)
    )


def start_subscribe(db: Session, account: Account) -> Subscription:
    """The `incomplete` subscription row for a new (or still-live)
    Checkout Session; `checkout_url` is where to send the participant.

    In order: ensure the account's one Stripe Customer (created and
    stored before anything else, so a later failure cannot mint a second
    one); compute the credit; mint the per-account coupon when it is
    positive; write the row `incomplete`; create the session; stamp the
    session id, URL, and `livemode` on the row before returning it.
    Credit is *not* consumed here — `credited_to_subscription_id` is set
    only by the webhook that confirms the first invoice was paid with
    the discount, so an abandoned session leaves it intact."""
    errors = []
    if account.role != "participant":
        errors.append(
            f"{account.email} is a {account.role}; only participants can "
            "subscribe"
        )
    if account.email_verified_at is None:
        errors.append(
            f"{account.email} is not verified; verify your email address "
            "before subscribing"
        )
    if current(db, account) is not None:
        errors.append("you already have a current subscription")
    if errors:
        raise SubscriptionRuleViolation(errors)

    live = _live_incomplete(db, account)
    if live is not None:
        return live

    if account.stripe_customer_id is None:
        account.stripe_customer_id = stripe_gateway.create_customer(
            email=account.email, account_id=account.id
        )
        db.commit()

    payments = credit_payments(db, account)
    credit = credit_cents(db, account)
    payment_ids = [p.id for p in payments] if credit > 0 else []
    coupon_id = None
    if credit > 0:
        coupon_id = stripe_gateway.create_credit_coupon(
            amount_cents=credit,
            currency=PAYMENT_CURRENCY,
            account_id=account.id,
            payment_ids=payment_ids,
        )

    origin = settings.cors_origins_list[0]
    subscription = Subscription(account_id=account.id, status="incomplete")
    db.add(subscription)
    db.flush()  # the row id rides in the session and subscription metadata
    try:
        session = stripe_gateway.create_subscription_checkout_session(
            price_id=settings.stripe_subscription_price_id,
            customer_id=account.stripe_customer_id,
            coupon_id=coupon_id,
            account_id=account.id,
            subscription_id=subscription.id,
            payment_ids=payment_ids,
            # Stripe substitutes the literal {CHECKOUT_SESSION_ID}.
            success_url=(
                f"{origin}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}"
            ),
            cancel_url=f"{origin}/subscribe",
        )
    except stripe_gateway.StripeGatewayError:
        db.rollback()
        raise
    subscription.stripe_checkout_session_id = session.id
    subscription.checkout_url = session.url
    subscription.livemode = session.livemode
    db.commit()
    return subscription


def portal_url(db: Session, account: Account) -> str:
    """A Stripe Customer Portal session for the account's Customer."""
    if account.stripe_customer_id is None or latest(db, account) is None:
        raise SubscriptionRuleViolation(
            ["you have no subscription to manage"]
        )
    origin = settings.cors_origins_list[0]
    return stripe_gateway.create_portal_session(
        customer_id=account.stripe_customer_id, return_url=f"{origin}/account"
    )


# --- the webhook -------------------------------------------------------------
#
# Called by `payments.handle_event` after its idempotency check; each
# handler mutates and returns, and `handle_event` records the event and
# commits — one transaction per event. Never raises: every failure mode
# is a loud log line and a quiet 200, because Stripe retries non-2xx
# responses forever.


def _period_of(obj: dict) -> tuple[datetime | None, datetime | None]:
    """The period as the subscription object carries it: at the top level
    on older API versions, on the subscription item since 2025-03-31
    (basil). Copied, whichever it is."""
    start, end = obj.get("current_period_start"), obj.get("current_period_end")
    if start is None and end is None:
        items = ((obj.get("items") or {}).get("data")) or []
        if items:
            start = items[0].get("current_period_start")
            end = items[0].get("current_period_end")
    return _ts(start), _ts(end)


def apply_subscription_object(subscription: Subscription, obj: dict) -> None:
    """Copy status, period, cancellation, and `livemode` from a Stripe
    subscription object onto the row. Never infer; copy. A field the
    object does not carry leaves the stored value alone."""
    if obj.get("status"):
        subscription.status = obj["status"]
    start, end = _period_of(obj)
    if start is not None:
        subscription.current_period_start = start
    if end is not None:
        subscription.current_period_end = end
    if "cancel_at_period_end" in obj:
        subscription.cancel_at_period_end = bool(obj["cancel_at_period_end"])
    if "canceled_at" in obj:
        subscription.canceled_at = _ts(obj["canceled_at"])
    if obj.get("livemode") is not None:
        subscription.livemode = obj["livemode"]


def _subscription_from_object(db: Session, obj: dict) -> Subscription | None:
    """The row for a Stripe subscription object: by Stripe's subscription
    id, else by the row id in the metadata the session stamped on it (so
    an `updated` that outruns the session's `completed` still lands)."""
    stripe_id = obj.get("id")
    row = None
    if stripe_id:
        row = db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_id
            )
        )
    if row is None:
        row_id = (obj.get("metadata") or {}).get("subscription_id")
        if row_id and str(row_id).isdigit():
            row = db.get(Subscription, int(row_id))
            if row is not None and row.stripe_subscription_id is None and stripe_id:
                row.stripe_subscription_id = stripe_id
    return row


def handle_checkout_completed(db: Session, event: dict) -> None:
    """A subscription-mode session completed: link Stripe's subscription
    id, re-stamp `livemode`, record the discount Stripe reported and mark
    the credited payments (one transaction with everything else), and
    copy status and period from the subscription object — which the
    session does not carry, so it is retrieved once. A session id with
    no row logs loudly and answers 200 (018's orphan rule)."""
    obj = event["data"]["object"]
    subscription = get_by_session_id(db, obj.get("id") or "")
    if subscription is None:
        logger.error(
            "stripe event %s: completed subscription session %s names no "
            "subscription row; investigate in the Stripe dashboard",
            event["id"],
            obj.get("id"),
        )
        return
    stripe_id = _id_of(obj.get("subscription"))
    if stripe_id:
        subscription.stripe_subscription_id = stripe_id
    livemode = obj.get("livemode", event.get("livemode"))
    if livemode is not None:
        subscription.livemode = livemode

    discount = int((obj.get("total_details") or {}).get("amount_discount") or 0)
    if discount > 0 and subscription.credit_applied_cents == 0:
        subscription.credit_applied_cents = discount
        raw_ids = (obj.get("metadata") or {}).get("credited_payment_ids") or ""
        for raw in raw_ids.split(","):
            if not raw.strip().isdigit():
                continue
            payment = db.get(Payment, int(raw))
            if (
                payment is not None
                and payment.account_id == subscription.account_id
                and payment.credited_to_subscription_id is None
            ):
                payment.credited_to_subscription_id = subscription.id

    if stripe_id:
        try:
            apply_subscription_object(
                subscription, stripe_gateway.retrieve_subscription(stripe_id)
            )
        except stripe_gateway.StripeGatewayError as exc:
            logger.error(
                "stripe event %s: subscription %s could not be retrieved "
                "(%s); status stays %s until customer.subscription.updated "
                "arrives",
                event["id"],
                stripe_id,
                exc,
                subscription.status,
            )


def handle_subscription_event(db: Session, event: dict) -> None:
    """`customer.subscription.updated` / `.deleted`: copy status, period,
    `cancel_at_period_end`, and `canceled_at` from the object. A deleted
    subscription arrives with status `canceled`; copying it is the whole
    handling — enrollments started under it are untouched (each keeps
    its own year, 9.02.2(3))."""
    obj = event["data"]["object"]
    subscription = _subscription_from_object(db, obj)
    if subscription is None:
        logger.error(
            "stripe event %s: %s for unknown subscription %s",
            event["id"],
            event["type"],
            obj.get("id"),
        )
        return
    apply_subscription_object(subscription, obj)


def _invoice_subscription(db: Session, invoice: dict) -> Subscription | None:
    """The row an invoice belongs to: by the subscription id the invoice
    names (top-level on older API versions, under `parent` since basil),
    else by the metadata the session stamped on the subscription."""
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    stripe_id = _id_of(invoice.get("subscription")) or _id_of(
        details.get("subscription")
    )
    row = None
    if stripe_id:
        row = db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_id
            )
        )
    if row is None:
        metadata = details.get("metadata") or (
            invoice.get("subscription_details") or {}
        ).get("metadata") or {}
        row_id = metadata.get("subscription_id")
        if row_id and str(row_id).isdigit():
            row = db.get(Subscription, int(row_id))
    return row


def _invoice_period(invoice: dict) -> tuple[datetime | None, datetime | None]:
    """The invoice's service period from its lines: earliest start,
    latest end — the numbers Stripe printed, copied."""
    lines = ((invoice.get("lines") or {}).get("data")) or []
    starts = [l["period"]["start"] for l in lines if (l.get("period") or {}).get("start")]
    ends = [l["period"]["end"] for l in lines if (l.get("period") or {}).get("end")]
    return (_ts(min(starts)) if starts else None, _ts(max(ends)) if ends else None)


def _invoice_payment_intent(invoice: dict) -> str | None:
    """Top-level `payment_intent` on older API versions; under
    `payments.data[].payment.payment_intent` since basil."""
    direct = _id_of(invoice.get("payment_intent"))
    if direct:
        return direct
    for record in ((invoice.get("payments") or {}).get("data")) or []:
        intent = _id_of((record.get("payment") or {}).get("payment_intent"))
        if intent:
            return intent
    return None


def _upsert_invoice(
    db: Session, subscription: Subscription, invoice: dict, status: str
) -> SubscriptionInvoice:
    row = db.scalar(
        select(SubscriptionInvoice).where(
            SubscriptionInvoice.stripe_invoice_id == invoice["id"]
        )
    )
    if row is None:
        row = SubscriptionInvoice(
            subscription_id=subscription.id,
            stripe_invoice_id=invoice["id"],
            amount_paid_cents=0,
            currency=invoice.get("currency") or PAYMENT_CURRENCY,
            status=status,
        )
        db.add(row)
    if row.status != "refunded":
        # A refund mark is superCPE's own and outlives later invoice
        # events for the same invoice.
        row.status = status
    if invoice.get("amount_paid") is not None:
        row.amount_paid_cents = int(invoice["amount_paid"])
    if invoice.get("currency"):
        row.currency = invoice["currency"]
    start, end = _invoice_period(invoice)
    if start is not None:
        row.period_start = start
    if end is not None:
        row.period_end = end
    intent = _invoice_payment_intent(invoice)
    if intent:
        row.stripe_payment_intent_id = intent
    if invoice.get("livemode") is not None:
        row.livemode = invoice["livemode"]
    return row


def handle_invoice_paid(db: Session, event: dict) -> None:
    """The renewal event (and the first invoice too): upsert the invoice
    row as `paid` and sync the subscription's period from the invoice
    lines. Status is not touched here — Stripe moves a `past_due`
    subscription back to `active` itself and says so in
    `customer.subscription.updated`."""
    invoice = event["data"]["object"]
    subscription = _invoice_subscription(db, invoice)
    if subscription is None:
        logger.error(
            "stripe event %s: invoice %s paid for unknown subscription",
            event["id"],
            invoice.get("id"),
        )
        return
    row = _upsert_invoice(db, subscription, invoice, "paid")
    if row.period_start is not None:
        subscription.current_period_start = row.period_start
    if row.period_end is not None:
        subscription.current_period_end = row.period_end
    if invoice.get("livemode") is not None:
        subscription.livemode = invoice["livemode"]


def handle_invoice_payment_failed(db: Session, event: dict) -> None:
    """A failed charge: the invoice row as `open`, nothing else. The
    subscription's status follows the next `customer.subscription.updated`
    (Stripe moves it to `past_due` itself). No email of superCPE's own —
    Stripe's dunning emails are the operator's dashboard step."""
    invoice = event["data"]["object"]
    subscription = _invoice_subscription(db, invoice)
    if subscription is None:
        logger.error(
            "stripe event %s: invoice %s failed for unknown subscription",
            event["id"],
            invoice.get("id"),
        )
        return
    _upsert_invoice(db, subscription, invoice, "open")


def mark_invoice_refunded(db: Session, charge: dict) -> bool:
    """`charge.refunded` on a subscription invoice: mark the invoice row
    `refunded` and stop — no status change, no voiding, no cancellation.
    The admin subscriptions view flags it; cancelling in Stripe is the
    admin's separate act (refund runbook), and the webhook then syncs
    the status. Returns False when no invoice row matches, so the caller
    can try 018's payments (or log an unknown refund)."""
    invoice_id = _id_of(charge.get("invoice"))
    intent_id = _id_of(charge.get("payment_intent"))
    row = None
    if invoice_id:
        row = db.scalar(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.stripe_invoice_id == invoice_id
            )
        )
    if row is None and intent_id:
        row = db.scalar(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.stripe_payment_intent_id == intent_id
            )
        )
    if row is None:
        return False
    row.status = "refunded"
    return True


def refunded(subscription: Subscription) -> bool:
    return any(i.status == "refunded" for i in subscription.invoices)
