"""The Stripe webhook (018): the sole creator of enrollments.

Unauthenticated by session — Stripe cannot log in — so the signature
check is the whole authentication: anything unsigned or wrongly signed
is refused with 400. A verified event always answers 200, however it
was handled: Stripe retries non-2xx responses forever, and every
failure mode inside is a loud log line instead.

026 took this route out from behind `require_site_open_or_session`, a
deliberate reversal of 018's "allowlist untouched". The 009 gate exists
so a closed site does not advertise what is behind it; this route
discloses no course, price, participant, or credit figure — an unsigned
request gets the same bare 400 in either mode, and a signed one is
Stripe's. Answering in coming_soon is what lets the whole transport
(DNS, TLS, Caddy, signature verification) be proven against production
with sandbox keys before the flip, instead of on opening day.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import payments, stripe_gateway

router = APIRouter()


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe_gateway.verify_webhook(payload, signature)
    except stripe_gateway.WebhookSignatureError:
        raise HTTPException(
            status_code=400, detail="Invalid webhook signature"
        )
    payments.handle_event(db, event)
    return {"received": True}
