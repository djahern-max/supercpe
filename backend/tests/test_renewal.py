"""Feature 028: unlimited re-takes and free renewal after expiry.

A participant who paid for a course never pays for it again. After the
one-year enrollment expires (9.02.2(3), unchanged), they start a new
enrollment at no charge through `POST /courses/{code}/renew` — 010's one
constructor with `source="renewal"`, no Stripe call, no payment row.
Eligibility is derived from payment and enrollment rows every time;
nothing is written except the new enrollment. The unlimited re-take
tests themselves live beside 010's in `test_completion.py` and
`test_policies.py`.
"""

from datetime import timedelta

from app.models.attempt import Attempt
from app.models.enrollment import Enrollment, ReviewAnswer
from app.models.payment import Payment
from app.services import enrollments as enrollments_service
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_completion import answer_all_reviews, expire, sit
from tests.test_enrollments import (
    make_published_course,
    update_to_v2_and_republish,
)
from tests.test_payments import (
    open_shop,
    pay,
    post_webhook,
    refund_event,
    start_checkout,
)
from tests.test_payments import stripe_boundary as _stripe_boundary

# The stubbed Stripe boundary, made available to this module by name.
stripe_boundary = _stripe_boundary

MY_COURSES_URL = "/api/v1/my/courses"


def renew(client, course_code="GOLD"):
    return client.post(f"/api/v1/courses/{course_code}/renew")


def only_enrollment(db, participant):
    [enrollment] = enrollments_service.list_for_account(db, participant)
    return enrollment


def errors_of(response):
    assert response.status_code == 422, response.json()
    return response.json()["errors"]


# --- the happy path ---------------------------------------------------------


def test_paid_and_expired_renews_at_no_charge(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)
    old = only_enrollment(db_session, participant)
    answer_all_reviews(db_session, old)
    failed = sit(db_session, old, wrong=4)
    assert failed.status == "failed"
    expire(db_session, old)

    # The card says so before the click.
    [card] = client.get(MY_COURSES_URL).json()
    assert card["status"] == "expired"
    assert card["renewable"] is True

    response = renew(client)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "active"
    assert body["enrollment_id"] != old.id
    assert body["renewable"] is False
    assert body["review_answered"] == 0
    assert body["failed_attempts"] == 0
    assert body["open_attempt_id"] is None

    new = db_session.get(Enrollment, body["enrollment_id"])
    assert new.source == "renewal"
    assert new.created_by_account_id is None
    assert new.expires_at - new.enrolled_at == timedelta(days=365)
    assert new.expires_at > old.expires_at
    # The old enrollment's clock is untouched (never extended).
    db_session.refresh(old)
    assert enrollments_service.status(old) == "expired"

    # Nothing but the enrollment was written: no payment row, no answers,
    # no attempts on the new one.
    assert db_session.query(Payment).count() == 1
    assert db_session.get(Payment, payment.id).status == "paid"
    assert (
        db_session.query(ReviewAnswer).filter_by(enrollment_id=new.id).count()
        == 0
    )
    assert db_session.query(Attempt).filter_by(enrollment_id=new.id).count() == 0
    # ...and the old enrollment keeps its record (retention).
    assert (
        db_session.query(ReviewAnswer).filter_by(enrollment_id=old.id).count()
        == 2
    )
    assert db_session.query(Attempt).filter_by(enrollment_id=old.id).count() == 1

    # Second call while the renewal is active: refused, no duplicate.
    again = renew(client)
    [error] = errors_of(again)
    assert "still active" in error
    assert len(enrollments_service.list_for_account(db_session, participant)) == 2

    cards = client.get(MY_COURSES_URL).json()
    assert [c["status"] for c in cards] == ["active", "expired"]
    assert [c["renewable"] for c in cards] == [False, False]


def test_renewal_pins_the_current_published_packages(
    client, db_session, admin_account, stripe_boundary
):
    """010 pins at enrollment: a renewal reads the course as published
    now, not the expired enrollment's version."""
    course, participant = open_shop(client, db_session)
    pay(client, db_session)
    old = only_enrollment(db_session, participant)
    expire(db_session, old)
    [package] = enrollments_service.packages_for(db_session, old)
    v2 = update_to_v2_and_republish(db_session, course, package)

    response = renew(client)
    assert response.status_code == 201, response.json()
    new = db_session.get(Enrollment, response.json()["enrollment_id"])
    assert new.package_versions == {str(v2.id): 2}
    # The expired one still serves v1.
    assert old.package_versions == {str(package.id): 1}


def test_expired_enrollment_stays_readable_after_renewal(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    pay(client, db_session)
    old = only_enrollment(db_session, participant)
    answer_all_reviews(db_session, old)
    attempt = sit(db_session, old, wrong=4)
    expire(db_session, old)
    assert renew(client).status_code == 201

    detail = client.get(f"/api/v1/my/enrollments/{old.id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "expired"
    assert detail.json()["review_answered"] == 2
    assert detail.json()["failed_attempts"] == 1
    history = client.get(
        f"/api/v1/my/enrollments/{old.id}/assessment/attempts/{attempt.id}"
    )
    assert history.status_code == 200
    assert history.json()["status"] == "failed"

    # The admin list shows both rows with their sources.
    client.cookies.clear()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    rows = client.get(
        f"/api/v1/admin/courses/{course.course_code}/enrollments"
    ).json()
    assert sorted((r["source"], r["status"]) for r in rows) == [
        ("purchase", "expired"),
        ("renewal", "active"),
    ]


# --- the refusal matrix -----------------------------------------------------


def test_paid_and_active_refused(client, db_session, admin_account, stripe_boundary):
    open_shop(client, db_session)
    pay(client, db_session)
    [error] = errors_of(renew(client))
    assert "still active" in error and "expiring" in error


def test_paid_and_completed_refused(
    client, db_session, admin_account, stripe_boundary
):
    from tests.test_completion import complete_profile

    complete_profile(db_session)
    open_shop(client, db_session)
    pay(client, db_session)
    participant_enrollment = only_enrollment(
        db_session,
        db_session.query(Enrollment).one().account,
    )
    answer_all_reviews(db_session, participant_enrollment)
    assert sit(db_session, participant_enrollment).status == "passed"
    [error] = errors_of(renew(client))
    assert "already completed" in error

    # Even once the completed enrollment's year is over.
    expire(db_session, participant_enrollment)
    assert enrollments_service.status(participant_enrollment) == "completed"
    [error] = errors_of(renew(client))
    assert "already completed" in error


def test_refunded_and_expired_refused(
    client, db_session, admin_account, stripe_boundary
):
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)
    assert post_webhook(client, refund_event(payment)).status_code == 200
    old = only_enrollment(db_session, participant)
    expire(db_session, old)
    [error] = errors_of(renew(client))
    assert "not purchased" in error
    [card] = client.get(MY_COURSES_URL).json()
    assert card["renewable"] is False


def test_voided_refused_and_checkout_reopens(
    client, db_session, admin_account, stripe_boundary
):
    """Acceptance 4: refunded, then voided, then expired — no renewal
    button, and checkout is allowed again (never paid successfully, in
    effect)."""
    course, participant = open_shop(client, db_session)
    payment = pay(client, db_session)
    assert post_webhook(client, refund_event(payment)).status_code == 200
    old = only_enrollment(db_session, participant)
    enrollments_service.void(db_session, old, admin_account)
    old.expires_at = old.expires_at - timedelta(days=400)
    db_session.commit()
    assert enrollments_service.status(old) == "voided"

    errors = errors_of(renew(client))
    assert any("not purchased" in e for e in errors)
    assert any("voided" in e for e in errors)
    [card] = client.get(MY_COURSES_URL).json()
    assert card["status"] == "voided"
    assert card["renewable"] is False

    fresh = start_checkout(client)
    assert fresh.status_code == 201, fresh.json()
    assert len(stripe_boundary.created) == 2


def test_never_paid_and_expired_refused(
    client, db_session, admin_account, stripe_boundary
):
    """A goodwill or admin-created enrollment (010's CLI, say): the
    Enroll/price button, not a renewal."""
    course, participant = open_shop(client, db_session)
    old = enrollments_service.enroll(
        db_session, participant, course, created_by=admin_account
    )
    expire(db_session, old)
    [error] = errors_of(renew(client))
    assert "not purchased" in error
    [card] = client.get(MY_COURSES_URL).json()
    assert card["status"] == "expired"
    assert card["renewable"] is False
    assert start_checkout(client).status_code == 201


def test_no_enrollment_at_all_refused(
    client, db_session, admin_account, stripe_boundary
):
    open_shop(client, db_session)
    errors = errors_of(renew(client))
    assert any("not purchased" in e for e in errors)
    assert any("no enrollment" in e for e in errors)


def test_unpublished_and_unknown_course_refused(
    client, db_session, admin_account, stripe_boundary
):
    from app.services import courses as courses_service

    course, participant = open_shop(client, db_session)
    pay(client, db_session)
    expire(db_session, only_enrollment(db_session, participant))
    courses_service.unpublish(db_session, course)
    [error] = errors_of(renew(client))
    assert "draft" in error and "published" in error
    assert renew(client, "NOPE").status_code == 404


def test_only_the_latest_expired_enrollment_is_renewable(
    client, db_session, admin_account, stripe_boundary
):
    """Two expired enrollments on one course (a renewal that also ran
    out): only the most recent card offers the button, and renewing
    again still works."""
    course, participant = open_shop(client, db_session)
    pay(client, db_session)
    first = only_enrollment(db_session, participant)
    expire(db_session, first)
    assert renew(client).status_code == 201
    second = next(
        e
        for e in enrollments_service.list_for_account(db_session, participant)
        if e.id != first.id
    )
    expire(db_session, second)
    cards = client.get(MY_COURSES_URL).json()
    by_id = {c["enrollment_id"]: c["renewable"] for c in cards}
    assert by_id == {second.id: True, first.id: False}
    assert renew(client).status_code == 201


# --- the gate ---------------------------------------------------------------


def test_renew_404s_anonymously_while_coming_soon(client, db_session):
    make_published_course(db_session)
    assert renew(client).status_code == 404


def test_renew_needs_a_participant_session_once_open(
    client, db_session, admin_account, stripe_boundary
):
    open_shop(client, db_session)
    client.cookies.clear()
    assert renew(client).status_code == 401
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert renew(client).status_code == 403
