"""The Stripe boundary (018): every Stripe API call and signature check
lives here and nowhere else. Tests stub this module; nothing in the test
suite touches the network. The dependency is the official `stripe`
package — hand-rolling Checkout Session creation or webhook signature
verification (HMAC with tolerance windows) would be more code and less
trustworthy, the same justification as boto3 (012).

Card data never transits superCPE: checkout is Stripe's hosted page
(a redirect), so the PCI surface is a URL.
"""

from dataclasses import dataclass

import stripe

from app.config import settings


class StripeGatewayError(Exception):
    """Stripe refused or the network failed; the caller turns this into a
    502 without leaking the underlying exception text to a participant."""


class WebhookSignatureError(Exception):
    """The webhook payload is unsigned or wrongly signed."""


@dataclass
class CheckoutSession:
    """What superCPE keeps of a created Checkout Session: the id, where
    to send the participant, the amount/currency exactly as Stripe
    reported them back, and (026) whether Stripe says the session is a
    live-mode one."""

    id: str
    url: str
    payment_intent_id: str | None
    amount_cents: int
    currency: str
    livemode: bool | None


def create_checkout_session(
    *,
    course_title: str,
    course_code: str,
    price_cents: int,
    currency: str,
    account_id: int,
    payment_id: int,
    customer_email: str,
    success_url: str,
    cancel_url: str,
) -> CheckoutSession:
    """One payment-mode hosted Checkout Session for one course. The
    metadata carries what the webhook needs to find its own records;
    Stripe sends its own receipt email (superCPE sends no payment email
    of its own — the receipt toggle is an ops step in OPERATIONS.md)."""
    try:
        session = stripe.checkout.Session.create(
            api_key=settings.stripe_secret_key,
            mode="payment",
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency,
                        "unit_amount": price_cents,
                        "product_data": {"name": course_title},
                    },
                }
            ],
            customer_email=customer_email,
            metadata={
                "account_id": str(account_id),
                "course_code": course_code,
                "payment_id": str(payment_id),
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return CheckoutSession(
        id=session["id"],
        url=session["url"],
        payment_intent_id=session["payment_intent"],
        amount_cents=session["amount_total"],
        currency=session["currency"],
        livemode=session.get("livemode"),
    )


def verify_webhook(payload: bytes, signature_header: str) -> dict:
    """The signed event as a plain dict, or WebhookSignatureError for
    anything unsigned or wrongly signed. The only authentication a
    webhook has — Stripe cannot log in."""
    try:
        event = stripe.Webhook.construct_event(
            payload, signature_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise WebhookSignatureError(str(exc)) from exc
    return event.to_dict()


# --- 029: Stripe Billing --------------------------------------------------
#
# The same boundary, extended — never a second client. Subscriptions ride
# the same account, keys, and webhook endpoint as 018's checkouts. Each
# function returns exactly what superCPE keeps and nothing it would have to
# interpret; the objects the webhook delivers are read by the same
# `services.subscriptions` code that reads what `retrieve_subscription`
# returns, so a fact is copied from Stripe the same way whichever road it
# arrived by.


@dataclass
class SubscriptionCheckoutSession:
    """What superCPE keeps of a created subscription-mode Checkout
    Session: the id, where to send the participant, and Stripe's own
    `livemode` (026)."""

    id: str
    url: str
    livemode: bool | None


def create_customer(*, email: str, account_id: int) -> str:
    """The one durable Stripe Customer for an account, created on the
    first subscription checkout and stored on the account (the id is the
    only thing kept). Returns the customer id."""
    try:
        customer = stripe.Customer.create(
            api_key=settings.stripe_secret_key,
            email=email,
            metadata={"account_id": str(account_id)},
        )
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return customer["id"]


def create_credit_coupon(
    *,
    amount_cents: int,
    currency: str,
    account_id: int,
    payment_ids: list[int],
) -> str:
    """A single-use, once-only, amount-off coupon carrying the account's
    course-purchase credit onto the first invoice. Per-account by
    construction — no shared promo code, no reuse: `max_redemptions=1`
    and `duration="once"` are Stripe's own guards, and the metadata names
    the account and the payments credited. Returns the coupon id."""
    try:
        coupon = stripe.Coupon.create(
            api_key=settings.stripe_secret_key,
            amount_off=amount_cents,
            currency=currency,
            duration="once",
            max_redemptions=1,
            name="Course purchase credit",
            metadata={
                "account_id": str(account_id),
                "credited_payment_ids": ",".join(str(i) for i in payment_ids),
            },
        )
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return coupon["id"]


def create_subscription_checkout_session(
    *,
    price_id: str,
    customer_id: str,
    coupon_id: str | None,
    account_id: int,
    subscription_id: int,
    payment_ids: list[int],
    success_url: str,
    cancel_url: str,
) -> SubscriptionCheckoutSession:
    """One subscription-mode hosted Checkout Session for the configured
    yearly Price. `payment_method_collection="always"` makes Stripe
    collect a card even when the credit coupon brings the first invoice
    to $0, so the renewal has something to charge. The metadata rides on
    both the session and the subscription it creates, so every later
    event (session completed, subscription updated, invoice paid) can
    find superCPE's row whichever arrives first."""
    metadata = {
        "account_id": str(account_id),
        "subscription_id": str(subscription_id),
        "credited_payment_ids": ",".join(str(i) for i in payment_ids),
    }
    params = dict(
        api_key=settings.stripe_secret_key,
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        payment_method_collection="always",
        metadata=metadata,
        subscription_data={"metadata": metadata},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    if coupon_id is not None:
        params["discounts"] = [{"coupon": coupon_id}]
    try:
        session = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return SubscriptionCheckoutSession(
        id=session["id"], url=session["url"], livemode=session.get("livemode")
    )


def retrieve_subscription(subscription_id: str) -> dict:
    """The subscription object as a plain dict — the same shape the
    webhook delivers in `data.object`, read by the same code. Called once
    from the completed-session handler, because the Checkout Session
    object itself carries neither the subscription's status nor its
    period, and copying beats inferring."""
    try:
        subscription = stripe.Subscription.retrieve(
            subscription_id, api_key=settings.stripe_secret_key
        )
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return subscription.to_dict()


def create_portal_session(*, customer_id: str, return_url: str) -> str:
    """A Stripe Customer Portal session: cancellation, card update, and
    invoice history live there; superCPE builds none of them. What the
    portal allows is its dashboard configuration (OPERATIONS.md)."""
    try:
        session = stripe.billing_portal.Session.create(
            api_key=settings.stripe_secret_key,
            customer=customer_id,
            return_url=return_url,
        )
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return session["url"]


def retrieve_price(price_id: str) -> tuple[int | None, str | None]:
    """The configured Price's unit amount (cents) and currency, for
    preflight's comparison against `SUBSCRIPTION_PRICE_CENTS`. The
    displayed price is the constant; the charged price is this."""
    try:
        price = stripe.Price.retrieve(
            price_id, api_key=settings.stripe_secret_key
        )
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc)) from exc
    return price.get("unit_amount"), price.get("currency")
