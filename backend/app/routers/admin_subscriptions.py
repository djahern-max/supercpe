"""Admin subscriptions view (029): the Billing paper trail with the two
loud flags. No actions beyond 018's enrollment void, which the page
offers beside each active enrollment of a refunded subscription.
Refunds and cancellations are done in the Stripe dashboard (refund
runbook); the webhook then syncs what Stripe reports."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.subscription import Subscription
from app.schemas.subscription import (
    AdminSubscriptionEnrollmentOut,
    AdminSubscriptionInvoiceOut,
    AdminSubscriptionOut,
)
from app.services import subscriptions as subscriptions_service

router = APIRouter(
    prefix="/admin", dependencies=[Depends(require_role("admin"))]
)


def _subscription_out(db: Session, subscription: Subscription) -> AdminSubscriptionOut:
    refunded = subscriptions_service.refunded(subscription)
    active = (
        subscriptions_service.active_subscription_enrollments(
            db, subscription.account
        )
        if refunded
        else []
    )
    return AdminSubscriptionOut(
        id=subscription.id,
        email=subscription.account.email,
        display_name=subscription.account.display_name,
        stripe_subscription_id=subscription.stripe_subscription_id,
        stripe_customer_id=subscription.account.stripe_customer_id,
        status=subscription.status,
        current=subscriptions_service.is_current(subscription),
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=subscription.canceled_at,
        credit_applied_cents=subscription.credit_applied_cents,
        livemode=subscription.livemode,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        invoices=[
            AdminSubscriptionInvoiceOut(
                id=invoice.id,
                stripe_invoice_id=invoice.stripe_invoice_id,
                stripe_payment_intent_id=invoice.stripe_payment_intent_id,
                amount_paid_cents=invoice.amount_paid_cents,
                currency=invoice.currency,
                status=invoice.status,
                period_start=invoice.period_start,
                period_end=invoice.period_end,
                livemode=invoice.livemode,
                created_at=invoice.created_at,
            )
            for invoice in subscription.invoices
        ],
        refunded_with_current_subscription=(
            refunded and subscriptions_service.is_current(subscription)
        ),
        refunded_with_active_enrollments=refunded and bool(active),
        active_enrollments=[
            AdminSubscriptionEnrollmentOut(
                enrollment_id=e.id,
                course_code=e.course.course_code,
                expires_at=e.expires_at,
            )
            for e in active
        ],
    )


@router.get("/subscriptions", response_model=list[AdminSubscriptionOut])
def list_subscriptions(db: Session = Depends(get_db)):
    return [
        _subscription_out(db, subscription)
        for subscription in subscriptions_service.list_all(db)
    ]
