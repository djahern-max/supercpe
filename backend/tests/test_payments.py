"""Feature 018: Stripe checkout.

Every Stripe call goes through the stubbed boundary
(`services.stripe_gateway`); no test touches the network. The webhook is
the sole creator of enrollments — the tests prove exactly-once creation
across replays, that a refund marks the payment and touches nothing else,
and that the guarded void action is where access actually ends.
"""

import itertools
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.payment import Payment, StripeWebhookEvent
from app.services import enrollments as enrollments_service
from app.services import stripe_gateway
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_config import make_settings
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    make_participant,
    make_publish_ready_course,
    make_published_course,
)
from tests.test_site import SITE_MODE_URL, open_the_site

CHECKOUT_URL = "/api/v1/checkout"
WEBHOOK_URL = "/api/v1/stripe/webhook"
ADMIN_PAYMENTS_URL = "/api/v1/admin/payments"

TEST_SIGNATURE = "t=1,v1=stubbed-valid"


@pytest.fixture
def stripe_boundary(monkeypatch):
    """Stubs the whole Stripe boundary: session creation returns a fake
    hosted-page URL and records the call; webhook verification accepts
    exactly TEST_SIGNATURE and hands back the JSON payload as the event."""
    calls = SimpleNamespace(created=[])
    counter = itertools.count(1)

    def fake_create_checkout_session(**kwargs):
        n = next(counter)
        calls.created.append(kwargs)
        return stripe_gateway.CheckoutSession(
            id=f"cs_test_{n}",
            url=f"https://checkout.stripe.com/c/pay/cs_test_{n}",
            payment_intent_id=None,
            amount_cents=kwargs["price_cents"],
            currency=kwargs["currency"],
        )

    def fake_verify_webhook(payload, signature_header):
        if signature_header != TEST_SIGNATURE:
            raise stripe_gateway.WebhookSignatureError("bad signature")
        return json.loads(payload)

    monkeypatch.setattr(
        stripe_gateway, "create_checkout_session", fake_create_checkout_session
    )
    monkeypatch.setattr(stripe_gateway, "verify_webhook", fake_verify_webhook)
    return calls


def open_shop(client, db_session, course_code="GOLD"):
    """A published course, the site open, and a verified participant
    signed in — the scene every purchase starts from."""
    course, package = make_published_course(db_session, course_code)
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    open_the_site(client)
    client.cookies.clear()
    participant = make_participant(db_session)
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    return course, participant


def start_checkout(client, course_code="GOLD"):
    return client.post(CHECKOUT_URL, json={"course_code": course_code})


def post_webhook(client, event, signature=TEST_SIGNATURE):
    return client.post(
        WEBHOOK_URL,
        content=json.dumps(event),
        headers={
            "stripe-signature": signature,
            "Content-Type": "application/json",
        },
    )


def completed_event(payment, event_id="evt_completed_1"):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "payment_intent": "pi_test_1",
                "amount_total": payment.amount_cents,
                "currency": payment.currency,
                "metadata": {"payment_id": str(payment.id)},
            }
        },
    }


def pay(client, db_session, course_code="GOLD"):
    """Checkout plus the completed webhook: the paid payment row."""
    started = start_checkout(client, course_code)
    assert started.status_code == 201, started.json()
    payment = db_session.get(Payment, started.json()["payment_id"])
    assert post_webhook(client, completed_event(payment)).status_code == 200
    db_session.refresh(payment)
    return payment


# --- publish requires a price (business rule) --------------------------------


def test_publish_refuses_priceless_course_as_business_rule(
    client, db_session, admin_headers
):
    from tests.conftest import publish_test_policies
    from tests.test_enrollments import make_recorder

    course, _ = make_publish_ready_course(db_session)
    publish_test_policies(db_session, make_recorder(db_session))
    course.price_cents = None
    db_session.commit()

    response = client.post(
        f"/api/v1/admin/courses/{course.course_code}/publish"
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    # Worded as superCPE's own rule, listed apart from disclosure items.
    assert "business rule" in error
    assert "8.01" not in error.split("not an")[0]

    # The admin readiness view carries the same finding.
    detail = client.get(f"/api/v1/admin/courses/{course.course_code}").json()
    assert "price_missing" in [f["code"] for f in detail["readiness"]]

    client.put(
        f"/api/v1/admin/courses/{course.course_code}/price",
        json={"price_cents": 4900},
    )
    published = client.post(
        f"/api/v1/admin/courses/{course.course_code}/publish"
    )
    assert published.status_code == 200, published.json()
    assert published.json()["price_cents"] == 4900


def test_price_must_be_a_positive_integer(client, db_session, admin_headers):
    course, _ = make_publish_ready_course(db_session)
    for bad in (0, -100):
        response = client.put(
            f"/api/v1/admin/courses/{course.course_code}/price",
            json={"price_cents": bad},
        )
        assert response.status_code == 422, response.json()


def test_public_payloads_carry_the_price(client, db_session, admin_headers):
    course, _ = make_published_course(db_session)
    [summary] = client.get("/api/v1/courses").json()
    assert summary["price_cents"] == 4900
    detail = client.get(f"/api/v1/courses/{course.course_code}").json()
    assert detail["price_cents"] == 4900


# --- checkout ----------------------------------------------------------------


def test_checkout_returns_session_url_and_writes_pending_row(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    response = start_checkout(client)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")

    payment = db_session.get(Payment, body["payment_id"])
    assert payment.status == "pending"
    assert payment.account_id == participant.id
    assert payment.course_id == course.id
    assert payment.amount_cents == 4900
    assert payment.currency == "usd"
    assert payment.stripe_checkout_session_id == "cs_test_1"

    # The session was created with the metadata the webhook needs, the
    # participant's email for Stripe's receipt, and integer cents.
    [call] = stripe_boundary.created
    assert call["payment_id"] == payment.id
    assert call["account_id"] == participant.id
    assert call["course_code"] == "GOLD"
    assert call["price_cents"] == 4900
    assert call["customer_email"] == PARTICIPANT_EMAIL
    assert "{CHECKOUT_SESSION_ID}" in call["success_url"]
    assert call["cancel_url"].endswith("/courses/GOLD")


def test_checkout_refusal_matrix(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)

    # Unknown course: 404, nothing minted.
    assert start_checkout(client, "NOPE").status_code == 404

    # Unpublished course: a distinct refusal.
    draft, _ = make_publish_ready_course(db_session, "DRAFT")
    response = start_checkout(client, "DRAFT")
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "draft" in error and "published" in error

    # Already actively enrolled: refused, naming the expiry.
    pay(client, db_session)
    response = start_checkout(client)
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "active enrollment" in error and "after it expires" in error

    assert db_session.query(Payment).count() == 1


def test_expired_enrollment_allows_a_fresh_purchase(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    first = pay(client, db_session)
    enrollment = enrollments_service.list_for_account(db_session, participant)[0]
    enrollment.expires_at = enrollment.expires_at - timedelta(days=400)
    db_session.commit()

    # Re-purchase creates a fresh payment and, on the webhook, a fresh
    # enrollment; the old one is history.
    second = start_checkout(client)
    assert second.status_code == 201, second.json()
    payment = db_session.get(Payment, second.json()["payment_id"])
    assert payment.id != first.id
    event = completed_event(payment, event_id="evt_completed_2")
    assert post_webhook(client, event).status_code == 200
    enrollments = enrollments_service.list_for_account(db_session, participant)
    assert len(enrollments) == 2
    statuses = sorted(enrollments_service.status(e) for e in enrollments)
    assert statuses == ["active", "expired"]


def test_live_pending_session_is_returned_not_duplicated(
    client, db_session, admin_account, stripe_boundary
):
    open_shop(client, db_session)
    first = start_checkout(client)
    second = start_checkout(client)
    assert second.status_code == 201
    assert second.json() == first.json()
    assert len(stripe_boundary.created) == 1
    assert db_session.query(Payment).count() == 1

    # An abandoned session past the Checkout lifetime is not returned; a
    # new one is minted.
    payment = db_session.get(Payment, first.json()["payment_id"])
    payment.created_at = payment.created_at - timedelta(hours=25)
    db_session.commit()
    third = start_checkout(client)
    assert third.json()["payment_id"] != first.json()["payment_id"]
    assert len(stripe_boundary.created) == 2


# --- the webhook -------------------------------------------------------------


def test_completed_webhook_creates_exactly_one_enrollment_across_replays(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    started = start_checkout(client)
    payment = db_session.get(Payment, started.json()["payment_id"])
    event = completed_event(payment)

    assert post_webhook(client, event).status_code == 200
    db_session.refresh(payment)
    assert payment.status == "paid"
    # Amount and intent as Stripe reported them on the event.
    assert payment.stripe_payment_intent_id == "pi_test_1"

    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    assert enrollment.source == "purchase"
    assert enrollment.created_by_account_id is None
    assert enrollments_service.status(enrollment) == "active"
    # 9.02.2(3): one year from the date of purchase.
    assert enrollment.expires_at - enrollment.enrolled_at == timedelta(days=365)

    # A replayed event id answers 200 and changes nothing.
    assert post_webhook(client, event).status_code == 200
    # A duplicate completion under a fresh event id changes nothing either.
    assert post_webhook(
        client, completed_event(payment, event_id="evt_completed_dup")
    ).status_code == 200
    db_session.expire_all()
    assert (
        len(enrollments_service.list_for_account(db_session, participant)) == 1
    )
    assert db_session.query(StripeWebhookEvent).count() == 2

    # The success page's poll now names the enrollment.
    status = client.get(
        f"{CHECKOUT_URL}/{payment.stripe_checkout_session_id}/status"
    )
    assert status.json()["status"] == "paid"
    assert status.json()["enrollment_id"] == enrollment.id


def test_unsigned_webhook_is_refused(
    client, db_session, admin_account, stripe_boundary
):
    open_shop(client, db_session)
    event = {"id": "evt_x", "type": "checkout.session.completed", "data": {"object": {}}}
    assert post_webhook(client, event, signature="").status_code == 400
    assert post_webhook(client, event, signature="t=1,v1=wrong").status_code == 400
    assert db_session.query(StripeWebhookEvent).count() == 0


def test_webhook_tolerates_a_missing_payment_row(
    client, db_session, admin_account, stripe_boundary, caplog
):
    """Metadata pointing at a row a rollback ate: log loudly, answer 200,
    never 500 — Stripe retries 500s forever."""
    open_shop(client, db_session)
    event = {
        "id": "evt_orphan",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_gone", "metadata": {"payment_id": "999"}}},
    }
    with caplog.at_level("ERROR"):
        assert post_webhook(client, event).status_code == 200
    assert any("names no payment row" in r.message for r in caplog.records)
    # Recorded, so a retry of the same broken event stays quiet.
    assert db_session.query(StripeWebhookEvent).count() == 1


def test_unhandled_event_types_answer_200_and_are_logged_by_name(
    client, db_session, admin_account, stripe_boundary, caplog
):
    open_shop(client, db_session)
    event = {"id": "evt_odd", "type": "payment_intent.created", "data": {"object": {}}}
    with caplog.at_level("INFO"):
        assert post_webhook(client, event).status_code == 200
    assert any("payment_intent.created" in r.message for r in caplog.records)


def test_expired_session_webhook_marks_the_payment_expired(
    client, db_session, admin_account, stripe_boundary
):
    open_shop(client, db_session)
    started = start_checkout(client)
    payment = db_session.get(Payment, started.json()["payment_id"])
    event = {
        "id": "evt_expired_1",
        "type": "checkout.session.expired",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "metadata": {"payment_id": str(payment.id)},
            }
        },
    }
    assert post_webhook(client, event).status_code == 200
    db_session.refresh(payment)
    assert payment.status == "expired"


# --- refunds and the void action ---------------------------------------------


def refund_event(payment, event_id="evt_refund_1"):
    return {
        "id": event_id,
        "type": "charge.refunded",
        "data": {
            "object": {"payment_intent": payment.stripe_payment_intent_id}
        },
    }


def test_refund_marks_payment_and_leaves_enrollment_intact(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)

    assert post_webhook(client, refund_event(payment)).status_code == 200
    db_session.refresh(payment)
    assert payment.status == "refunded"
    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    assert enrollments_service.status(enrollment) == "active"

    # The admin payments view flags it loudly.
    client.cookies.clear()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    [row] = client.get(ADMIN_PAYMENTS_URL).json()
    assert row["status"] == "refunded"
    assert row["refunded_with_active_enrollment"] is True
    assert row["enrollment_id"] == enrollment.id
    assert row["amount_cents"] == 4900
    assert row["email"] == PARTICIPANT_EMAIL


def test_void_ends_access_and_is_logged(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)
    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    package_id = int(next(iter(enrollment.package_versions)))
    assert post_webhook(client, refund_event(payment)).status_code == 200

    client.cookies.clear()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    voided = client.post(f"/api/v1/admin/enrollments/{enrollment.id}/void")
    assert voided.status_code == 200, voided.json()
    assert voided.json()["status"] == "voided"
    assert voided.json()["voided_by_email"] == ADMIN_EMAIL
    db_session.refresh(enrollment)
    assert enrollment.voided_at is not None
    assert enrollment.voided_by_account_id == admin_account.id

    # A second void has nothing left to end.
    again = client.post(f"/api/v1/admin/enrollments/{enrollment.id}/void")
    assert again.status_code == 422

    # The flag clears: the refund's access question has been answered.
    [row] = client.get(ADMIN_PAYMENTS_URL).json()
    assert row["refunded_with_active_enrollment"] is False
    assert row["enrollment_status"] == "voided"

    # Access has actually ended for the participant.
    client.cookies.clear()
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    [summary] = client.get("/api/v1/my/courses").json()
    assert summary["status"] == "voided"
    assert summary["assessment_available"] is False
    play = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/lessons/{package_id}/play"
    )
    assert play.status_code == 403


def test_void_refuses_a_completed_enrollment(
    client, db_session, admin_account, stripe_boundary
):
    from app.models.enrollment import Completion

    course, participant = open_shop(client, db_session)
    pay(client, db_session)
    [enrollment] = enrollments_service.list_for_account(db_session, participant)
    db_session.add(
        Completion(
            enrollment_id=enrollment.id,
            attempt_id=_passing_attempt(db_session, enrollment).id,
            completed_at=enrollment.enrolled_at,
            credit_awarded=course.credit_award,
            field_of_study=course.field_of_study,
            certificate_number="2026-000001",
            verification_token="t" * 64,
            certificate_snapshot={},
        )
    )
    db_session.commit()

    client.cookies.clear()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = client.post(f"/api/v1/admin/enrollments/{enrollment.id}/void")
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "9.02" in error and "immutable" in error


def _passing_attempt(db_session, enrollment):
    from decimal import Decimal

    from app.models.attempt import Attempt

    attempt = Attempt(
        enrollment_id=enrollment.id,
        course_id=enrollment.course_id,
        is_preview=False,
        status="passed",
        question_count=4,
        passing_pct=Decimal("70.00"),
        started_at=enrollment.enrolled_at,
        submitted_at=enrollment.enrolled_at,
        package_versions=[],
    )
    db_session.add(attempt)
    db_session.commit()
    return attempt


# --- the status endpoint -----------------------------------------------------


def test_status_endpoint_is_owner_only(
    client, db_session, admin_account, stripe_boundary
):
    open_shop(client, db_session)
    started = start_checkout(client)
    payment = db_session.get(Payment, started.json()["payment_id"])
    url = f"{CHECKOUT_URL}/{payment.stripe_checkout_session_id}/status"

    pending = client.get(url)
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert pending.json()["enrollment_id"] is None
    assert pending.json()["course_code"] == "GOLD"
    assert "support_email" in pending.json()

    # Another participant: 404, not 403 — whose payment this is, is
    # nobody else's business. An unknown session id looks the same.
    client.cookies.clear()
    make_participant(db_session, email="other@supercpe.test")
    login(client, "other@supercpe.test", PARTICIPANT_PASSWORD)
    assert client.get(url).status_code == 404
    assert client.get(f"{CHECKOUT_URL}/cs_missing/status").status_code == 404


# --- mode matrix and the open gate -------------------------------------------


def test_018_routes_404_anonymously_in_coming_soon(client, db_session):
    """Acceptance 5, beyond the 015 router walk in test_site (which
    covers these routes by construction): the three 018 routes answer
    404 to anonymous requests while the site is coming_soon."""
    assert client.post(CHECKOUT_URL, json={"course_code": "GOLD"}).status_code == 404
    assert client.get(f"{CHECKOUT_URL}/cs_x/status").status_code == 404
    assert client.post(WEBHOOK_URL, content=b"{}").status_code == 404


def test_open_gate_refuses_without_stripe_config_and_passes_with_it(
    client, db_session, admin_account, admin_headers, monkeypatch
):
    make_published_course(db_session)
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    refused = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert refused.status_code == 422
    assert any(
        "Stripe is not configured" in e and "STRIPE_WEBHOOK_SECRET" in e
        for e in refused.json()["errors"]
    )
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_dummy")
    open_the_site(client)


def test_stripe_config_is_all_or_nothing_at_boot():
    violations = boot_violations_for(stripe_secret_key="sk_test_x")
    assert any("STRIPE_PUBLISHABLE_KEY" in v for v in violations)
    assert any("STRIPE_WEBHOOK_SECRET" in v for v in violations)
    assert boot_violations_for() == []
    assert (
        boot_violations_for(
            stripe_secret_key="sk_test_x",
            stripe_publishable_key="pk_test_x",
            stripe_webhook_secret="whsec_x",
        )
        == []
    )


def boot_violations_for(**overrides):
    from app.config import boot_violations

    return boot_violations(make_settings(**overrides))
