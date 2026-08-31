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
    to send the participant, and the amount/currency exactly as Stripe
    reported them back."""

    id: str
    url: str
    payment_intent_id: str | None
    amount_cents: int
    currency: str


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
