"""The Stripe webhook (018): the sole creator of enrollments.

Unauthenticated by session — Stripe cannot log in — so the signature
check is the whole authentication: anything unsigned or wrongly signed
is refused with 400. Behind `require_site_open_or_session` like every
018 route, it 404s while the site is coming_soon (no payments exist to
confirm before open). A verified event always answers 200, however it
was handled: Stripe retries non-2xx responses forever, and every
failure mode inside is a loud log line instead.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_site_open_or_session
from app.db import get_db
from app.services import payments, stripe_gateway

router = APIRouter(dependencies=[Depends(require_site_open_or_session)])


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
