"""The annual subscription (029): the offer, the subscribe flow, the
success-page poll, the account's own view, and the Customer Portal.

Every route sits behind `require_site_open_or_session` like the catalog —
404 anonymously while the site is coming_soon. The offer is readable by
anyone at open (a visitor sees the page with sign-in links); everything
else needs the participant role. Nothing here names a course, a course
price, a credit figure, or the Registry: the disclosure is about the
subscription (8.01 items 8 and 9, 8.01.1), and the policies are linked,
never restated.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import optional_account, require_role, require_site_open_or_session
from app.constants.payments import PAYMENT_CURRENCY
from app.constants.subscription import (
    SUBSCRIPTION_PERIOD_DAYS,
    SUBSCRIPTION_PRICE_CENTS,
)
from app.db import get_db
from app.models.account import Account
from app.routers.courses import policy_link
from app.schemas.package import ValidationErrors
from app.schemas.subscription import (
    MySubscriptionOut,
    PortalOut,
    SubscribeOfferOut,
    SubscribeStarted,
    SubscribeStatusOut,
)
from app.services import sponsor as sponsor_service
from app.services import stripe_gateway
from app.services import subscriptions as subscriptions_service
from app.services.subscriptions import SubscriptionRuleViolation

router = APIRouter(
    prefix="/subscribe",
    dependencies=[Depends(require_site_open_or_session)],
)

participant = require_role("participant")

PROVIDER_UNREACHABLE = (
    "The payment provider could not be reached. Nothing was charged; try "
    "again in a moment."
)


@router.get("", response_model=SubscribeOfferOut)
def offer(
    db: Session = Depends(get_db),
    account: Account | None = Depends(optional_account),
):
    is_participant = account is not None and account.role == "participant"
    credit = subscriptions_service.credit_cents(db, account) if is_participant else 0
    subscribed = (
        is_participant and subscriptions_service.current(db, account) is not None
    )
    return SubscribeOfferOut(
        price_cents=SUBSCRIPTION_PRICE_CENTS,
        currency=PAYMENT_CURRENCY,
        period_days=SUBSCRIPTION_PERIOD_DAYS,
        credit_cents=credit,
        pay_today_cents=SUBSCRIPTION_PRICE_CENTS - credit,
        subscribed=subscribed,
        registration_policy=policy_link(db, "registration"),
        refund_policy=policy_link(db, "refund"),
    )


@router.post(
    "",
    response_model=SubscribeStarted,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def subscribe(
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    try:
        subscription = subscriptions_service.start_subscribe(db, account)
    except SubscriptionRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    except stripe_gateway.StripeGatewayError:
        # The detail stays in the server log.
        return JSONResponse(
            status_code=502, content={"errors": [PROVIDER_UNREACHABLE]}
        )
    return SubscribeStarted(
        subscription_id=subscription.id,
        checkout_url=subscription.checkout_url,
    )


def _state(subscription) -> str:
    if subscription is None or (
        subscription.status == "incomplete"
        and subscription.stripe_subscription_id is None
    ):
        return "none"
    if subscriptions_service.is_current(subscription):
        return (
            "cancels_at_period_end"
            if subscription.cancel_at_period_end
            else "current"
        )
    if subscription.status == "past_due":
        return "past_due"
    return "lapsed"


@router.get("/me", response_model=MySubscriptionOut)
def my_subscription(
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    subscription = subscriptions_service.latest(db, account)
    state = _state(subscription)
    if state == "none":
        return MySubscriptionOut(
            state="none",
            status=None,
            current_period_end=None,
            cancel_at_period_end=False,
            canceled_at=None,
            credit_applied_cents=0,
            manageable=False,
        )
    return MySubscriptionOut(
        state=state,
        status=subscription.status,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=subscription.canceled_at,
        credit_applied_cents=subscription.credit_applied_cents,
        manageable=account.stripe_customer_id is not None,
    )


@router.post(
    "/portal",
    response_model=PortalOut,
    responses={422: {"model": ValidationErrors}},
)
def portal(
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    try:
        url = subscriptions_service.portal_url(db, account)
    except SubscriptionRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    except stripe_gateway.StripeGatewayError:
        return JSONResponse(
            status_code=502, content={"errors": [PROVIDER_UNREACHABLE]}
        )
    return PortalOut(url=url)


@router.get("/{session_id}/status", response_model=SubscribeStatusOut)
def subscribe_status(
    session_id: str,
    db: Session = Depends(get_db),
    account: Account = Depends(participant),
):
    """Owner-only: a foreign session id is a 404, not a 403 (018)."""
    subscription = subscriptions_service.get_by_session_id(db, session_id)
    if subscription is None or subscription.account_id != account.id:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return SubscribeStatusOut(
        status=subscription.status,
        current=subscriptions_service.is_current(subscription),
        credit_applied_cents=subscription.credit_applied_cents,
        current_period_end=subscription.current_period_end,
        support_email=sponsor_service.get_profile(db).contact_email,
    )
