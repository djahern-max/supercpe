"""Feature 029: the annual subscription.

Every Stripe call goes through the stubbed boundary; no test touches the
network. Entitlement is derived from what Stripe last reported; a
subscriber's enroll is a click with no Stripe call; credit is consumed
only by the webhook that confirmed the discounted invoice; a refund marks
and stops.
"""

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.constants.subscription import SUBSCRIPTION_PRICE_CENTS
from app.models.enrollment import Enrollment
from app.models.payment import Payment, StripeWebhookEvent
from app.models.subscription import Subscription, SubscriptionInvoice
from app.services import enrollments as enrollments_service
from app.services import stripe_gateway
from app.services import subscriptions as subscriptions_service
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    make_participant,
    make_publish_ready_course,
    make_published_course,
)
from tests.test_payments import (
    TEST_SIGNATURE,
    completed_event,
    open_shop,
    pay,
    post_webhook,
    refund_event,
    start_checkout,
)
from tests.test_payments import stripe_boundary as _stripe_boundary
from tests.test_site import open_the_site

stripe_boundary = _stripe_boundary

SUBSCRIBE_URL = "/api/v1/subscribe"
MY_COURSES_URL = "/api/v1/my/courses"
ADMIN_SUBSCRIPTIONS_URL = "/api/v1/admin/subscriptions"
ADMIN_PAYMENTS_URL = "/api/v1/admin/payments"


def now_ts():
    return int(datetime.now(timezone.utc).timestamp())


YEAR = 365 * 24 * 3600


@pytest.fixture
def billing_boundary(monkeypatch, stripe_boundary):
    """The Billing half of the boundary, on top of 018's stub: customers,
    coupons, subscription-mode sessions, the portal, the one retrieve."""
    calls = SimpleNamespace(
        customers=[], coupons=[], sessions=[], portals=[], retrieved=[]
    )
    counter = itertools.count(1)
    # What `retrieve_subscription` answers, keyed by Stripe id; a test
    # sets it to shape the completed-session handler's copy.
    calls.subscription_objects = {}

    def fake_create_customer(**kwargs):
        calls.customers.append(kwargs)
        return f"cus_test_{len(calls.customers)}"

    def fake_create_credit_coupon(**kwargs):
        calls.coupons.append(kwargs)
        return f"coupon_test_{len(calls.coupons)}"

    def fake_create_subscription_checkout_session(**kwargs):
        n = next(counter)
        calls.sessions.append(kwargs)
        return stripe_gateway.SubscriptionCheckoutSession(
            id=f"cs_sub_{n}",
            url=f"https://checkout.stripe.com/c/pay/cs_sub_{n}",
            livemode=False,
        )

    def fake_retrieve_subscription(subscription_id):
        calls.retrieved.append(subscription_id)
        if subscription_id in calls.subscription_objects:
            return calls.subscription_objects[subscription_id]
        raise stripe_gateway.StripeGatewayError("no such subscription")

    def fake_create_portal_session(**kwargs):
        calls.portals.append(kwargs)
        return "https://billing.stripe.com/p/session/test_1"

    monkeypatch.setattr(stripe_gateway, "create_customer", fake_create_customer)
    monkeypatch.setattr(
        stripe_gateway, "create_credit_coupon", fake_create_credit_coupon
    )
    monkeypatch.setattr(
        stripe_gateway,
        "create_subscription_checkout_session",
        fake_create_subscription_checkout_session,
    )
    monkeypatch.setattr(
        stripe_gateway, "retrieve_subscription", fake_retrieve_subscription
    )
    monkeypatch.setattr(
        stripe_gateway, "create_portal_session", fake_create_portal_session
    )
    return calls


def subscription_object(
    stripe_id,
    row_id,
    status="active",
    start=None,
    end=None,
    cancel_at_period_end=False,
    canceled_at=None,
    livemode=False,
):
    """A Stripe subscription object in the basil shape: the period lives
    on the item, not the top level."""
    start = now_ts() - 60 if start is None else start
    end = start + YEAR if end is None else end
    return {
        "id": stripe_id,
        "object": "subscription",
        "status": status,
        "cancel_at_period_end": cancel_at_period_end,
        "canceled_at": canceled_at,
        "livemode": livemode,
        "metadata": {"subscription_id": str(row_id)},
        "items": {
            "data": [
                {"current_period_start": start, "current_period_end": end}
            ]
        },
    }


def completed_session_event(
    row, stripe_id="sub_test_1", discount=0, event_id="evt_sub_completed_1", livemode=False
):
    credited = ",".join(
        str(p.id)
        for p in row.account_credit_payments
    ) if hasattr(row, "account_credit_payments") else ""
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": row.stripe_checkout_session_id,
                "mode": "subscription",
                "subscription": stripe_id,
                "livemode": livemode,
                "total_details": {"amount_discount": discount},
                "metadata": {
                    "subscription_id": str(row.id),
                    "credited_payment_ids": credited,
                },
            }
        },
    }


def subscription_event(obj, event_type="customer.subscription.updated", event_id=None):
    return {
        "id": event_id or f"evt_{event_type}_{obj['id']}_{obj['status']}",
        "type": event_type,
        "data": {"object": obj},
    }


def invoice_event(
    stripe_sub_id,
    row_id,
    invoice_id="in_test_1",
    event_type="invoice.paid",
    amount_paid=14900,
    start=None,
    end=None,
    event_id=None,
    payment_intent="pi_sub_1",
    livemode=False,
):
    start = now_ts() if start is None else start
    end = start + YEAR if end is None else end
    return {
        "id": event_id or f"evt_{event_type}_{invoice_id}",
        "type": event_type,
        "data": {
            "object": {
                "id": invoice_id,
                "object": "invoice",
                "amount_paid": amount_paid,
                "currency": "usd",
                "livemode": livemode,
                "parent": {
                    "subscription_details": {
                        "subscription": stripe_sub_id,
                        "metadata": {"subscription_id": str(row_id)},
                    }
                },
                "payments": {
                    "data": [{"payment": {"payment_intent": payment_intent}}]
                },
                "lines": {"data": [{"period": {"start": start, "end": end}}]},
            }
        },
    }


def subscribe(client):
    return client.post(SUBSCRIBE_URL)


def pay_course(client, db, course_code):
    """018's checkout plus completion for one more course: 018's `pay`
    reuses one event id and one intent id, which is fine for a single
    purchase and a replay for a second."""
    started = start_checkout(client, course_code)
    assert started.status_code == 201, started.json()
    payment = db.get(Payment, started.json()["payment_id"])
    event = completed_event(payment, event_id=f"evt_completed_{course_code}")
    event["data"]["object"]["payment_intent"] = f"pi_{course_code}"
    assert post_webhook(client, event).status_code == 200
    db.refresh(payment)
    assert payment.status == "paid"
    return payment


def row_of(db, response):
    return db.get(Subscription, response.json()["subscription_id"])


def complete_subscription(client, db, billing, row, stripe_id="sub_test_1", discount=0, credited_ids=()):
    """The stubbed session completes: the completed event lands (with
    Stripe's subscription object retrievable), making the row current."""
    billing.subscription_objects[stripe_id] = subscription_object(stripe_id, row.id)
    event = completed_session_event(row, stripe_id=stripe_id, discount=discount)
    event["data"]["object"]["metadata"]["credited_payment_ids"] = ",".join(
        str(i) for i in credited_ids
    )
    assert post_webhook(client, event).status_code == 200
    db.expire_all()
    return event


def make_subscriber(client, db, billing):
    """A verified participant with a current subscription, signed in."""
    course, participant = open_shop(client, db)
    started = subscribe(client)
    assert started.status_code == 201, started.json()
    row = row_of(db, started)
    complete_subscription(client, db, billing, row)
    assert subscriptions_service.current(db, participant) is not None
    return course, participant, row


def errors_of(response):
    assert response.status_code == 422, response.json()
    return response.json()["errors"]


# --- entitlement -------------------------------------------------------------


@pytest.mark.parametrize(
    "status, end_offset, expected",
    [
        ("active", 3600, True),
        ("active", -3600, False),
        ("past_due", 3600, False),
        ("canceled", 3600, False),
        ("incomplete", 3600, False),
        ("unpaid", 3600, False),
        ("trialing", 3600, False),
    ],
)
def test_entitlement_is_derived_from_status_and_period(
    db_session, status, end_offset, expected
):
    participant = make_participant(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        Subscription(
            account_id=participant.id,
            stripe_subscription_id="sub_x",
            status=status,
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(seconds=end_offset),
        )
    )
    db_session.commit()
    assert (subscriptions_service.current(db_session, participant) is not None) is expected


def test_status_check_rejects_an_unknown_value(db_session):
    from sqlalchemy.exc import IntegrityError

    participant = make_participant(db_session)
    db_session.add(Subscription(account_id=participant.id, status="bogus"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- subscribing -------------------------------------------------------------


def test_subscribe_writes_incomplete_row_before_returning_the_url(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    response = subscribe(client)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")
    row = db_session.get(Subscription, body["subscription_id"])
    assert row.status == "incomplete"
    assert row.stripe_checkout_session_id == "cs_sub_1"
    assert row.stripe_subscription_id is None
    assert row.credit_applied_cents == 0
    assert row.livemode is False

    # The customer was created once and stored; the session named it and
    # the configured Price, and carried the row id in both metadatas.
    db_session.refresh(participant)
    assert participant.stripe_customer_id == "cus_test_1"
    [customer] = billing_boundary.customers
    assert customer["email"] == PARTICIPANT_EMAIL
    [session] = billing_boundary.sessions
    assert session["price_id"] == "price_dummy"
    assert session["customer_id"] == "cus_test_1"
    assert session["coupon_id"] is None
    assert session["subscription_id"] == row.id
    assert "{CHECKOUT_SESSION_ID}" in session["success_url"]
    assert session["cancel_url"].endswith("/subscribe")
    assert billing_boundary.coupons == []


def test_customer_is_created_once_and_reused(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    first = subscribe(client)
    row = row_of(db_session, first)
    # Let the session lapse, subscribe again: same customer, new session.
    row.created_at = row.created_at - timedelta(hours=25)
    db_session.commit()
    second = subscribe(client)
    assert second.json()["subscription_id"] != first.json()["subscription_id"]
    assert len(billing_boundary.customers) == 1
    assert len(billing_boundary.sessions) == 2
    assert billing_boundary.sessions[1]["customer_id"] == "cus_test_1"


def test_live_incomplete_session_is_reused_not_duplicated(
    client, db_session, admin_account, billing_boundary
):
    open_shop(client, db_session)
    first = subscribe(client)
    second = subscribe(client)
    assert second.status_code == 201
    assert second.json() == first.json()
    assert len(billing_boundary.sessions) == 1
    assert db_session.query(Subscription).count() == 1


def test_subscribe_refusal_matrix(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    # Unverified: refused before any Stripe call.
    participant.email_verified_at = None
    db_session.commit()
    [error] = errors_of(subscribe(client))
    assert "not verified" in error
    assert billing_boundary.customers == []
    participant.email_verified_at = datetime.now(timezone.utc)
    db_session.commit()

    # Already current: refused.
    started = subscribe(client)
    complete_subscription(client, db_session, billing_boundary, row_of(db_session, started))
    [error] = errors_of(subscribe(client))
    assert "already have a current subscription" in error
    assert len(billing_boundary.sessions) == 1


def test_credit_from_paid_uncredited_payments_only_capped(
    client, db_session, admin_account, billing_boundary
):
    """Two $49 purchases: the credit is the sum capped at the price; a
    refunded purchase counts for nothing; a pending one neither."""
    course, participant = open_shop(client, db_session)
    make_published_course(db_session, "SILV")
    make_published_course(db_session, "BRNZ")
    make_published_course(db_session, "PEND")
    first = pay_course(client, db_session, "GOLD")
    second = pay_course(client, db_session, "SILV")
    refunded = pay_course(client, db_session, "BRNZ")
    assert post_webhook(client, refund_event(refunded, "evt_refund_brnz")).status_code == 200
    db_session.refresh(refunded)
    assert refunded.status == "refunded"
    pending = start_checkout(client, "PEND")
    assert pending.status_code == 201

    offer = client.get(SUBSCRIBE_URL).json()
    assert offer["price_cents"] == SUBSCRIPTION_PRICE_CENTS == 14900
    assert offer["credit_cents"] == 9800
    assert offer["pay_today_cents"] == 5100
    assert offer["subscribed"] is False
    assert offer["registration_policy"]["url"] == "/policies#registration"
    assert offer["refund_policy"]["url"] == "/policies#refund"

    response = subscribe(client)
    assert response.status_code == 201, response.json()
    [coupon] = billing_boundary.coupons
    assert coupon["amount_cents"] == 9800
    assert coupon["currency"] == "usd"
    assert sorted(coupon["payment_ids"]) == sorted([first.id, second.id])
    [session] = billing_boundary.sessions
    assert session["coupon_id"] == "coupon_test_1"
    assert sorted(session["payment_ids"]) == sorted([first.id, second.id])
    # Nothing consumed yet: the session has not completed.
    db_session.expire_all()
    assert all(
        db_session.get(Payment, p.id).credited_to_subscription_id is None
        for p in (first, second, refunded)
    )


def test_credit_is_capped_at_the_subscription_price(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    course.price_cents = 9900
    make_published_course(db_session, "SILV")[0].price_cents = 9900
    db_session.commit()
    pay_course(client, db_session, "GOLD")
    pay_course(client, db_session, "SILV")
    offer = client.get(SUBSCRIBE_URL).json()
    assert offer["credit_cents"] == 14900
    assert offer["pay_today_cents"] == 0
    subscribe(client)
    [coupon] = billing_boundary.coupons
    assert coupon["amount_cents"] == 14900


def test_offer_for_a_visitor_at_open_names_no_course_and_no_credit(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    course.price_cents = 5300  # not a substring of the subscription price
    db_session.commit()
    client.cookies.clear()
    response = client.get(SUBSCRIBE_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["credit_cents"] == 0
    assert body["subscribed"] is False
    for fact in (course.title, course.course_code, str(course.price_cents), "National Registry"):
        assert fact not in response.text


# --- credit consumption ------------------------------------------------------


def test_abandoned_sessions_leave_the_credit_intact(
    client, db_session, admin_account, billing_boundary
):
    """Two abandoned sessions in a row: the payments stay uncredited and
    the third subscribe computes the same credit."""
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)
    for _ in range(2):
        started = subscribe(client)
        assert started.status_code == 201
        row = row_of(db_session, started)
        row.created_at = row.created_at - timedelta(hours=25)
        db_session.commit()
    db_session.expire_all()
    assert db_session.get(Payment, payment.id).credited_to_subscription_id is None
    assert client.get(SUBSCRIBE_URL).json()["credit_cents"] == 4900
    third = subscribe(client)
    assert third.status_code == 201
    assert len(billing_boundary.coupons) == 3
    assert all(c["amount_cents"] == 4900 for c in billing_boundary.coupons)


def test_completed_session_with_discount_consumes_the_credit_once(
    client, db_session, admin_account, billing_boundary
):
    """Acceptance 1: two $29 paid courses; the stubbed session completes
    with a $58 discount; credit_applied_cents is 5800 from the object,
    both payments carry the FK, the subscription is current, a replay
    changes nothing, and a second subscribe after a lapse computes
    zero credit."""
    course, participant = open_shop(client, db_session)
    course.price_cents = 2900
    make_published_course(db_session, "SILV")[0].price_cents = 2900
    db_session.commit()
    first = pay_course(client, db_session, "GOLD")
    second = pay_course(client, db_session, "SILV")
    offer = client.get(SUBSCRIBE_URL).json()
    assert (offer["credit_cents"], offer["pay_today_cents"]) == (5800, 9100)

    started = subscribe(client)
    row = row_of(db_session, started)
    event = complete_subscription(
        client, db_session, billing_boundary, row,
        discount=5800, credited_ids=[first.id, second.id],
    )
    db_session.refresh(row)
    assert row.status == "active"
    assert row.stripe_subscription_id == "sub_test_1"
    assert row.credit_applied_cents == 5800
    assert row.current_period_end is not None
    assert row.current_period_end > datetime.now(timezone.utc)
    assert db_session.get(Payment, first.id).credited_to_subscription_id == row.id
    assert db_session.get(Payment, second.id).credited_to_subscription_id == row.id
    assert billing_boundary.retrieved == ["sub_test_1"]

    # The success page's poll and the account view say so.
    status = client.get(f"{SUBSCRIBE_URL}/{row.stripe_checkout_session_id}/status").json()
    assert status["status"] == "active" and status["current"] is True
    assert status["credit_applied_cents"] == 5800
    me = client.get(f"{SUBSCRIBE_URL}/me").json()
    assert me["state"] == "current"
    assert me["credit_applied_cents"] == 5800
    assert me["current_period_end"] is not None
    assert me["manageable"] is True
    assert client.get("/api/v1/auth/me").json()["subscription_current"] is True

    # Replayed event: nothing changes.
    assert post_webhook(client, event).status_code == 200
    db_session.expire_all()
    assert db_session.query(StripeWebhookEvent).count() == 3  # two completions + this
    assert db_session.get(Subscription, row.id).credit_applied_cents == 5800

    # Lapse, then subscribe again: zero credit, no coupon.
    row = db_session.get(Subscription, row.id)
    row.status = "canceled"
    db_session.commit()
    assert client.get(SUBSCRIBE_URL).json()["credit_cents"] == 0
    again = subscribe(client)
    assert again.status_code == 201
    assert len(billing_boundary.coupons) == 1
    assert billing_boundary.sessions[1]["coupon_id"] is None

    # /admin/payments shows the credited marker.
    client.cookies.clear()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    rows = client.get(ADMIN_PAYMENTS_URL).json()
    assert {r["credited_to_subscription_id"] for r in rows} == {row.id}


def test_completed_session_retrieve_failure_leaves_status_for_the_update_event(
    client, db_session, admin_account, billing_boundary, caplog
):
    """The session object carries no status or period; when the one
    retrieve fails, the row stays `incomplete` (loudly) until
    customer.subscription.updated copies them."""
    course, participant = open_shop(client, db_session)
    row = row_of(db_session, subscribe(client))
    event = completed_session_event(row, stripe_id="sub_missing")
    with caplog.at_level("ERROR"):
        assert post_webhook(client, event).status_code == 200
    assert any("could not be retrieved" in r.message for r in caplog.records)
    db_session.refresh(row)
    assert row.stripe_subscription_id == "sub_missing"
    assert row.status == "incomplete"
    assert subscriptions_service.current(db_session, participant) is None

    obj = subscription_object("sub_missing", row.id)
    assert post_webhook(client, subscription_event(obj)).status_code == 200
    db_session.refresh(row)
    assert row.status == "active"
    assert subscriptions_service.current(db_session, participant) is not None


# --- enrolling under the subscription ----------------------------------------


def enroll(client, course_code="GOLD"):
    return client.post(f"/api/v1/courses/{course_code}/enroll")


def test_subscriber_enrolls_with_no_stripe_call(
    client, db_session, admin_account, billing_boundary
):
    """Acceptance 2: the enrollment is `subscription`-sourced with its
    own one-year clock; checkout for another course is refused as
    covered; a second enroll is refused."""
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    sessions_before = len(stripe_boundary_calls(billing_boundary))
    response = enroll(client)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "active"
    assert body["subscription_enrollable"] is False
    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    assert enrollment.source == "subscription"
    assert enrollment.created_by_account_id is None
    assert enrollment.expires_at - enrollment.enrolled_at == timedelta(days=365)
    assert db_session.query(Payment).count() == 0
    assert len(stripe_boundary_calls(billing_boundary)) == sessions_before

    make_published_course(db_session, "SILV")
    refused = start_checkout(client, "SILV")
    errors = errors_of(refused)
    assert any("subscription covers" in e for e in errors)
    assert db_session.query(Payment).count() == 0

    again = enroll(client)
    [error] = errors_of(again)
    assert "active enrollment" in error
    assert len(enrollments_service.list_for_account(db_session, participant)) == 1


def stripe_boundary_calls(billing):
    return billing.sessions + billing.customers + billing.coupons


def test_enroll_refusals(client, db_session, admin_account, billing_boundary):
    course, participant = open_shop(client, db_session)
    # Not a subscriber.
    [error] = errors_of(enroll(client))
    assert "do not have a current subscription" in error
    assert enroll(client, "NOPE").status_code == 404

    started = subscribe(client)
    complete_subscription(client, db_session, billing_boundary, row_of(db_session, started))
    # Unpublished course.
    make_publish_ready_course(db_session, "DRAFT")
    [error] = errors_of(enroll(client, "DRAFT"))
    assert "draft" in error and "published" in error
    # Completed: refused; expired: allowed (the subscriber's renewal).
    assert enroll(client).status_code == 201
    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    [card] = client.get(MY_COURSES_URL).json()
    assert card["status"] == "expired"
    assert card["subscription_enrollable"] is True
    assert card["renewable"] is False  # 028's route is for non-subscribers
    [error] = errors_of(client.post(f"/api/v1/courses/{course.course_code}/renew"))
    assert "subscription covers" in error
    renewed = enroll(client)
    assert renewed.status_code == 201, renewed.json()
    rows = enrollments_service.list_for_account(db_session, participant)
    assert [e.source for e in rows] == ["subscription", "subscription"]
    assert sorted(enrollments_service.status(e) for e in rows) == ["active", "expired"]
    cards = client.get(MY_COURSES_URL).json()
    assert [c["subscription_enrollable"] for c in cards] == [False, False]


def test_subscription_ending_leaves_enrollments_alone_and_028_renews_them(
    client, db_session, admin_account, billing_boundary
):
    """Acceptance 3: customer.subscription.deleted ends the entitlement;
    the enrollment is untouched and active; once expired, a lapsed
    subscriber renews it free through 028's route."""
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    assert enroll(client).status_code == 201
    [enrollment] = enrollments_service.list_for_account(db_session, participant)

    deleted = subscription_object(
        "sub_test_1", row.id, status="canceled", canceled_at=now_ts(), end=now_ts() - 1
    )
    assert post_webhook(
        client, subscription_event(deleted, "customer.subscription.deleted")
    ).status_code == 200
    db_session.expire_all()
    row = db_session.get(Subscription, row.id)
    assert row.status == "canceled"
    assert row.canceled_at is not None
    assert subscriptions_service.current(db_session, participant) is None
    assert client.get("/api/v1/auth/me").json()["subscription_current"] is False
    assert client.get(f"{SUBSCRIBE_URL}/me").json()["state"] == "lapsed"

    enrollment = db_session.get(Enrollment, enrollment.id)
    assert enrollments_service.status(enrollment) == "active"
    assert enrollment.voided_at is None
    [card] = client.get(MY_COURSES_URL).json()
    assert card["status"] == "active"

    # Not a subscriber any more: enroll refused, checkout refused (a
    # subscription-started course is not purchased again either).
    errors = errors_of(enroll(client))
    assert any("do not have a current subscription" in e for e in errors)

    enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    [card] = client.get(MY_COURSES_URL).json()
    assert card["status"] == "expired"
    assert card["renewable"] is True
    assert card["subscription_enrollable"] is False
    renewed = client.post(f"/api/v1/courses/{course.course_code}/renew")
    assert renewed.status_code == 201, renewed.json()
    assert renewed.json()["status"] == "active"
    rows = enrollments_service.list_for_account(db_session, participant)
    assert sorted(e.source for e in rows) == ["renewal", "subscription"]
    assert db_session.query(Payment).count() == 0


def test_renewal_is_refused_for_a_course_never_paid_nor_subscribed(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    enrollments_service.enroll(db_session, participant, course, created_by=None)
    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    errors = errors_of(client.post(f"/api/v1/courses/{course.course_code}/renew"))
    assert any("not purchased" in e and "subscription" in e for e in errors)


# --- webhook matrix ----------------------------------------------------------


def test_subscription_updated_copies_never_infers(
    client, db_session, admin_account, billing_boundary
):
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    start, end = now_ts() - 100, now_ts() + 12345
    obj = subscription_object(
        "sub_test_1", row.id, status="past_due", start=start, end=end,
        cancel_at_period_end=True, livemode=True,
    )
    event = subscription_event(obj)
    assert post_webhook(client, event).status_code == 200
    db_session.refresh(row)
    assert row.status == "past_due"
    assert int(row.current_period_start.timestamp()) == start
    assert int(row.current_period_end.timestamp()) == end
    assert row.cancel_at_period_end is True
    assert row.livemode is True
    assert subscriptions_service.current(db_session, participant) is None
    assert client.get(f"{SUBSCRIBE_URL}/me").json()["state"] == "past_due"

    # Replay: nothing changes, one event row per id.
    obj2 = subscription_object("sub_test_1", row.id, status="active", cancel_at_period_end=True)
    assert post_webhook(client, subscription_event(obj2, event_id=event["id"])).status_code == 200
    db_session.refresh(row)
    assert row.status == "past_due"
    assert post_webhook(client, subscription_event(obj2)).status_code == 200
    db_session.refresh(row)
    assert row.status == "active"
    assert client.get(f"{SUBSCRIBE_URL}/me").json()["state"] == "cancels_at_period_end"


def test_subscription_updated_arriving_before_completion_lands_by_metadata(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    row = row_of(db_session, subscribe(client))
    obj = subscription_object("sub_early", row.id)
    assert post_webhook(client, subscription_event(obj)).status_code == 200
    db_session.refresh(row)
    assert row.stripe_subscription_id == "sub_early"
    assert row.status == "active"


def test_unknown_subscription_and_orphan_session_log_and_answer_200(
    client, db_session, admin_account, billing_boundary, caplog
):
    open_shop(client, db_session)
    obj = subscription_object("sub_ghost", 999)
    orphan = {
        "id": "evt_orphan_sub",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_ghost", "mode": "subscription", "subscription": "sub_ghost"}},
    }
    with caplog.at_level("ERROR"):
        assert post_webhook(client, subscription_event(obj)).status_code == 200
        assert post_webhook(client, orphan).status_code == 200
        assert post_webhook(client, invoice_event("sub_ghost", 999)).status_code == 200
    messages = [r.message for r in caplog.records]
    assert any("unknown subscription" in m for m in messages)
    assert any("names no subscription row" in m for m in messages)
    assert any("unknown subscription" in m and "paid" in m for m in messages)
    assert db_session.query(StripeWebhookEvent).count() == 3
    assert db_session.query(Subscription).count() == 0


def test_invoice_paid_is_the_renewal_event(
    client, db_session, admin_account, billing_boundary
):
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    start = now_ts() + YEAR
    event = invoice_event("sub_test_1", row.id, "in_renewal", amount_paid=14900, start=start)
    assert post_webhook(client, event).status_code == 200
    db_session.expire_all()
    row = db_session.get(Subscription, row.id)
    [invoice] = row.invoices
    assert invoice.status == "paid"
    assert invoice.amount_paid_cents == 14900
    assert invoice.currency == "usd"
    assert invoice.stripe_payment_intent_id == "pi_sub_1"
    assert int(invoice.period_start.timestamp()) == start
    assert int(invoice.period_end.timestamp()) == start + YEAR
    assert invoice.livemode is False
    # The subscription's period followed the invoice lines.
    assert int(row.current_period_end.timestamp()) == start + YEAR
    assert subscriptions_service.current(db_session, participant) is not None

    # Replay: still one invoice row.
    assert post_webhook(client, event).status_code == 200
    db_session.expire_all()
    assert db_session.query(SubscriptionInvoice).count() == 1


def test_invoice_payment_failed_marks_open_and_touches_nothing_else(
    client, db_session, admin_account, billing_boundary
):
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    end_before = row.current_period_end
    event = invoice_event(
        "sub_test_1", row.id, "in_failed", event_type="invoice.payment_failed",
        amount_paid=0, payment_intent=None,
    )
    assert post_webhook(client, event).status_code == 200
    db_session.expire_all()
    row = db_session.get(Subscription, row.id)
    [invoice] = row.invoices
    assert invoice.status == "open"
    assert invoice.amount_paid_cents == 0
    assert row.status == "active"
    assert row.current_period_end == end_before
    # Later paid: the same row flips to paid.
    assert post_webhook(
        client, invoice_event("sub_test_1", row.id, "in_failed", amount_paid=14900)
    ).status_code == 200
    db_session.expire_all()
    [invoice] = db_session.get(Subscription, row.id).invoices
    assert invoice.status == "paid"


def test_refund_marks_the_invoice_and_stops(
    client, db_session, admin_account, billing_boundary
):
    """Acceptance 4: the invoice is `refunded`, both admin flags show,
    nothing is voided or cancelled; void from the existing action and the
    enrollment flag clears; a cancel synced from Stripe clears the other."""
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    assert post_webhook(client, invoice_event("sub_test_1", row.id, "in_first")).status_code == 200
    assert enroll(client).status_code == 201
    [enrollment] = enrollments_service.list_for_account(db_session, participant)

    charge = {
        "id": "evt_refund_sub",
        "type": "charge.refunded",
        "data": {"object": {"payment_intent": "pi_sub_1"}},
    }
    assert post_webhook(client, charge).status_code == 200
    db_session.expire_all()
    row = db_session.get(Subscription, row.id)
    [invoice] = row.invoices
    assert invoice.status == "refunded"
    assert row.status == "active"
    assert subscriptions_service.current(db_session, participant) is not None
    assert enrollments_service.status(db_session.get(Enrollment, enrollment.id)) == "active"

    client.cookies.clear()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    [admin_row] = client.get(ADMIN_SUBSCRIPTIONS_URL).json()
    assert admin_row["refunded_with_current_subscription"] is True
    assert admin_row["refunded_with_active_enrollments"] is True
    assert [e["enrollment_id"] for e in admin_row["active_enrollments"]] == [enrollment.id]
    assert admin_row["invoices"][0]["status"] == "refunded"
    assert admin_row["email"] == PARTICIPANT_EMAIL
    assert admin_row["stripe_customer_id"] == "cus_test_1"

    voided = client.post(f"/api/v1/admin/enrollments/{enrollment.id}/void")
    assert voided.status_code == 200, voided.json()
    [admin_row] = client.get(ADMIN_SUBSCRIPTIONS_URL).json()
    assert admin_row["refunded_with_active_enrollments"] is False
    assert admin_row["refunded_with_current_subscription"] is True

    canceled = subscription_object("sub_test_1", row.id, status="canceled", canceled_at=now_ts())
    assert post_webhook(
        client, subscription_event(canceled, "customer.subscription.deleted")
    ).status_code == 200
    [admin_row] = client.get(ADMIN_SUBSCRIPTIONS_URL).json()
    assert admin_row["refunded_with_current_subscription"] is False
    assert admin_row["status"] == "canceled"


def test_refund_for_a_course_payment_still_finds_the_payment(
    client, db_session, admin_account, billing_boundary
):
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)
    assert post_webhook(client, refund_event(payment)).status_code == 200
    db_session.refresh(payment)
    assert payment.status == "refunded"
    assert db_session.query(SubscriptionInvoice).count() == 0


def test_unknown_refund_logs_and_answers_200(
    client, db_session, admin_account, billing_boundary, caplog
):
    open_shop(client, db_session)
    charge = {"id": "evt_refund_ghost", "type": "charge.refunded",
              "data": {"object": {"payment_intent": "pi_ghost"}}}
    with caplog.at_level("ERROR"):
        assert post_webhook(client, charge).status_code == 200
    assert any("unknown payment intent" in r.message for r in caplog.records)


def test_unhandled_billing_types_answer_200(
    client, db_session, admin_account, billing_boundary, caplog
):
    open_shop(client, db_session)
    event = {"id": "evt_created", "type": "customer.subscription.created", "data": {"object": {}}}
    with caplog.at_level("INFO"):
        assert post_webhook(client, event).status_code == 200
    assert any("customer.subscription.created" in r.message for r in caplog.records)


# --- the portal and the status endpoint --------------------------------------


def test_portal_needs_a_customer_and_redirects(
    client, db_session, admin_account, billing_boundary
):
    open_shop(client, db_session)
    [error] = errors_of(client.post(f"{SUBSCRIBE_URL}/portal"))
    assert "no subscription to manage" in error
    subscribe(client)
    response = client.post(f"{SUBSCRIBE_URL}/portal")
    assert response.status_code == 200, response.json()
    assert response.json()["url"].startswith("https://billing.stripe.com/")
    [call] = billing_boundary.portals
    assert call["customer_id"] == "cus_test_1"
    assert call["return_url"].endswith("/account")


def test_status_endpoint_is_owner_only(
    client, db_session, admin_account, billing_boundary
):
    open_shop(client, db_session)
    row = row_of(db_session, subscribe(client))
    url = f"{SUBSCRIBE_URL}/{row.stripe_checkout_session_id}/status"
    pending = client.get(url).json()
    assert pending["status"] == "incomplete" and pending["current"] is False
    assert "support_email" in pending
    assert client.get(f"{SUBSCRIBE_URL}/me").json()["state"] == "none"

    client.cookies.clear()
    make_participant(db_session, email="other@supercpe.test")
    login(client, "other@supercpe.test", PARTICIPANT_PASSWORD)
    assert client.get(url).status_code == 404
    assert client.get(f"{SUBSCRIBE_URL}/cs_missing/status").status_code == 404


# --- the gate and the mode matrix --------------------------------------------


def test_new_routes_404_anonymously_in_coming_soon(client, db_session, billing_boundary):
    assert client.get(SUBSCRIBE_URL).status_code == 404
    assert client.post(SUBSCRIBE_URL).status_code == 404
    assert client.get(f"{SUBSCRIBE_URL}/me").status_code == 404
    assert client.post(f"{SUBSCRIBE_URL}/portal").status_code == 404
    assert client.get(f"{SUBSCRIBE_URL}/cs_x/status").status_code == 404
    assert client.post("/api/v1/courses/GOLD/enroll").status_code == 404
    assert client.get(ADMIN_SUBSCRIPTIONS_URL).status_code == 401


def test_no_new_route_carries_a_course_fact(
    client, db_session, admin_account, billing_boundary
):
    course, participant, row = make_subscriber(client, db_session, billing_boundary)
    course.price_cents = 5300  # not a substring of the subscription price
    db_session.commit()
    facts = [course.title, course.course_code, str(course.price_cents),
             str(course.credit_award), "National Registry", "national_registry"]
    responses = [
        client.get(SUBSCRIBE_URL),
        client.get(f"{SUBSCRIBE_URL}/me"),
        client.get(f"{SUBSCRIBE_URL}/{row.stripe_checkout_session_id}/status"),
        client.post(f"{SUBSCRIBE_URL}/portal"),
        client.post(SUBSCRIBE_URL),
    ]
    for response in responses:
        for fact in facts:
            assert fact not in response.text, (fact, response.text)


def test_open_gate_refuses_without_the_price_id(
    client, db_session, admin_account, admin_headers, monkeypatch
):
    make_published_course(db_session)
    monkeypatch.setattr(settings, "stripe_subscription_price_id", "")
    refused = client.put("/api/v1/admin/site-mode", json={"site_mode": "open"})
    assert refused.status_code == 422
    assert any(
        "Stripe is not configured" in e and "STRIPE_SUBSCRIPTION_PRICE_ID" in e
        for e in refused.json()["errors"]
    )
    monkeypatch.undo()
    open_the_site(client)


def test_migration_source_check_accepts_subscription(db_session):
    course, _ = make_published_course(db_session)
    participant = make_participant(db_session)
    enrollment = enrollments_service.enroll(
        db_session, participant, course, created_by=None, source="subscription"
    )
    assert db_session.get(Enrollment, enrollment.id).source == "subscription"


def test_webhook_signature_still_guards_billing_events(client, db_session, billing_boundary):
    event = subscription_event(subscription_object("sub_x", 1))
    assert post_webhook(client, event, signature="t=1,v1=wrong").status_code == 400
    assert post_webhook(client, event, signature=TEST_SIGNATURE).status_code == 200
