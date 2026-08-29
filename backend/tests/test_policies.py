"""Feature 011: the 8.01 items 8-11 policies, the launch gate on opening
the site, and the 4.05.3 item 4 instructions page.

The load-bearing rules: policies are append-only effective-dated versions
whose current one is derived; the re-take policy and the instructions are
rendered from the constants that enforce them so they can never drift; the
item 11 sponsor statement exists nowhere while `not_registered`; and 011's
new refusal — the site does not open while a policy is missing.
"""

from datetime import datetime, timedelta, timezone

from app.constants.assessment import PASSING_PCT, RETAKES_ALLOWED
from app.constants.enrollment import ENROLLMENT_DAYS
from app.services import policies
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    login,
    make_account,
    publish_test_policies,
)

POLICIES_URL = "/api/v1/policies"
ADMIN_POLICIES_URL = "/api/v1/admin/policies"
SITE_MODE_URL = "/api/v1/admin/site-mode"

PASSWORD = "a-long-enough-password"


def publish(client, kind, body=None, effective_at=None):
    payload = {"kind": kind, "body": body or f"The {kind} policy."}
    if effective_at is not None:
        payload["effective_at"] = effective_at.isoformat()
    response = client.post(ADMIN_POLICIES_URL, json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


# --- launch readiness -------------------------------------------------------


def test_no_versions_is_three_launch_missing_items(
    client, admin_headers, db_session
):
    body = client.get("/api/v1/admin/sponsor", headers=admin_headers).json()
    missing = [
        f for f in body["launch_findings"] if f["code"] == "policy_missing"
    ]
    assert len(missing) == 3
    assert all(f["level"] == "block" for f in missing)
    messages = " ".join(f["message"] for f in missing)
    assert "Registration and attendance" in messages
    assert "Refund and cancellation" in messages
    assert "Complaint resolution" in messages


def test_publishing_a_version_clears_its_item(client, admin_headers):
    publish(client, "refund")
    admin = client.get(ADMIN_POLICIES_URL).json()
    assert sorted(admin["missing"]) == ["complaint", "registration"]


def test_site_open_refused_naming_missing_policies_until_published(
    client, admin_headers, db_session
):
    refused = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert refused.status_code == 422
    errors = " ".join(refused.json()["errors"])
    assert "Refund and cancellation" in errors
    assert "Registration and attendance" in errors
    assert "Complaint resolution" in errors

    for kind in ("registration", "refund", "complaint"):
        publish(client, kind)
    opened = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert opened.status_code == 200, opened.json()


# --- versions ---------------------------------------------------------------


def test_future_effective_at_is_not_current_until_then(
    client, admin_headers, db_session
):
    publish(client, "refund", body="Refunds today.")
    publish(
        client,
        "refund",
        body="Refunds tomorrow.",
        effective_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    current = policies.current_version(db_session, "refund")
    assert current.body == "Refunds today."

    # Once its moment passes, the newer version takes over — same rows.
    future = [
        v
        for v in policies.versions_of(db_session, "refund")
        if v.body == "Refunds tomorrow."
    ][0]
    future.effective_at = datetime.now(timezone.utc)
    db_session.commit()
    assert (
        policies.current_version(db_session, "refund").body
        == "Refunds tomorrow."
    )


def test_history_retains_every_version(client, admin_headers):
    publish(client, "refund", body="Version one.")
    publish(client, "refund", body="Version two.")
    admin = client.get(ADMIN_POLICIES_URL).json()
    refund = [v for v in admin["history"] if v["kind"] == "refund"]
    assert [v["body"] for v in refund] == ["Version two.", "Version one."]
    assert [v["is_current"] for v in refund] == [True, False]
    assert all(v["created_by_email"] == ADMIN_EMAIL for v in refund)


def test_blank_body_refused(client, admin_headers):
    response = client.post(
        ADMIN_POLICIES_URL, json={"kind": "refund", "body": "   "}
    )
    assert response.status_code == 422


# --- the public payload -----------------------------------------------------


def test_public_route_gated_by_site_mode_exactly_as_courses(
    client, db_session, admin_account
):
    # Closed, no session: 404, like /courses.
    assert client.get(POLICIES_URL).status_code == 404
    assert client.get("/api/v1/how-it-works").status_code == 404

    # Any session passes the closed gate.
    make_account(db_session, "pat@supercpe.test", PASSWORD, "participant")
    login(client, "pat@supercpe.test", PASSWORD)
    assert client.get(POLICIES_URL).status_code == 200
    assert client.get("/api/v1/how-it-works").status_code == 200

    # Open: public.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    publish_test_policies(db_session, admin_account)
    assert (
        client.put(SITE_MODE_URL, json={"site_mode": "open"}).status_code
        == 200
    )
    client.cookies.clear()
    assert client.get(POLICIES_URL).status_code == 200
    assert client.get("/api/v1/how-it-works").status_code == 200


def test_retake_text_carries_the_enforced_numbers(client, admin_headers):
    payload = client.get(POLICIES_URL).json()
    assert str(RETAKES_ALLOWED) in payload["retake_policy"]
    assert str(PASSING_PCT) in payload["retake_policy"]
    assert str(ENROLLMENT_DAYS) in payload["retake_policy"]


def test_sponsor_statement_absent_while_not_registered(
    client, admin_headers, db_session
):
    publish(client, "registration")
    publish(client, "refund")
    publish(client, "complaint")
    response = client.get(POLICIES_URL)
    assert response.json()["sponsor_statement"] is None
    # Walk the whole payload: the words appear nowhere.
    assert "National Registry" not in response.text

    from app.services import sponsor as sponsor_service

    profile = sponsor_service.get_profile(db_session)
    profile.name = "superCPE"
    profile.registry_status = "registered"
    profile.national_registry_id = "112233"
    db_session.commit()
    statement = client.get(POLICIES_URL).json()["sponsor_statement"]
    assert statement is not None
    assert statement.startswith("superCPE is registered with")
    assert "National Registry of CPE Sponsors" in statement


def test_current_policies_carry_label_and_effective_date(
    client, admin_headers
):
    publish(client, "complaint", body="Write to us; we answer in 10 days.")
    payload = client.get(POLICIES_URL).json()
    [policy] = payload["policies"]
    assert policy["kind"] == "complaint"
    assert policy["label"] == "Complaint resolution"
    assert policy["body"] == "Write to us; we answer in 10 days."
    assert policy["effective_at"] is not None


def test_public_course_payload_links_policies_and_carries_outline(
    client, admin_headers, db_session
):
    from tests.test_enrollments import make_published_course

    course, _ = make_published_course(db_session)
    detail = client.get(f"/api/v1/courses/{course.course_code}").json()
    assert detail["policies_url"] == "/policies"
    [lesson] = detail["outline"]
    assert lesson["title"] == "Lesson GOLD-01"
    assert lesson["position"] == 1
    assert [o["id"] for o in lesson["objectives"]] == ["lo-1"]


# --- how it works -----------------------------------------------------------


def test_how_it_works_numbers_match_the_constants(client, admin_headers):
    markdown = client.get("/api/v1/how-it-works").json()["markdown"]
    assert f"{PASSING_PCT} percent" in markdown
    assert f"{RETAKES_ALLOWED} times" in markdown
    assert f"{ENROLLMENT_DAYS} days" in markdown
