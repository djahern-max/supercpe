"""Feature 017: self-registration and email verification.

The compliance-shaped tests are the constant-response assertions
(byte-identical 200s across the new / existing / deactivated branches,
with the outbound log proving which email actually went out), the login
refusals (unverified indistinguishable from wrong-password), and the
open-gate refusal without SMTP config. Raw verification tokens are read
from the console backend's log line — they are deliberately nowhere else.
"""

import logging
import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.account import Account, EmailVerificationToken
from app.models.email_message import EmailMessage
from app.services import auth as auth_service
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, make_account
from tests.test_enrollments import make_published_course
from tests.test_site import SITE_MODE_URL, open_the_site

REGISTER_URL = "/api/v1/register"
VERIFY_URL = "/api/v1/verify"
RESEND_URL = "/api/v1/resend-verification"
TEST_EMAIL_URL = "/api/v1/admin/email/test"
LOGIN_URL = "/api/v1/auth/login"

PAT = {
    "name": "Pat Example",
    "email": "pat@example.test",
    "password": "a-long-enough-password",
    "state": "NH",
}

TOKEN_RE = re.compile(r"/verify\?token=([A-Za-z0-9_\-]+)")


@pytest.fixture
def open_site(client, db_session, admin_headers, console_email):
    """The site open, the admin logged out, and every send routed through
    the console backend — the state a member of the public registers in."""
    make_published_course(db_session)
    open_the_site(client)
    client.cookies.clear()


def register(client, **overrides):
    return client.post(REGISTER_URL, json={**PAT, **overrides})


def outbound(db_session):
    return [
        (m.kind, m.recipient, m.backend)
        for m in db_session.scalars(
            select(EmailMessage).order_by(EmailMessage.id)
        )
    ]


def account_rows(db_session, email):
    return list(
        db_session.scalars(select(Account).where(Account.email == email))
    )


def last_token_from(caplog):
    matches = TOKEN_RE.findall(caplog.text)
    assert matches, "no verification link in the console email log"
    return matches[-1]


def register_and_grab_token(client, caplog, **overrides):
    with caplog.at_level(logging.INFO, logger="app.email"):
        response = register(client, **overrides)
    assert response.status_code == 200, response.json()
    return response, last_token_from(caplog)


# --- site-mode behavior ------------------------------------------------------


def test_all_public_routes_404_anonymously_in_coming_soon(client, db_session):
    assert client.post(REGISTER_URL, json=PAT).status_code == 404
    assert client.post(VERIFY_URL, json={"token": "x"}).status_code == 404
    assert (
        client.post(RESEND_URL, json={"email": PAT["email"]}).status_code
        == 404
    )
    # And none of it left a trace.
    assert account_rows(db_session, PAT["email"]) == []
    assert outbound(db_session) == []


def test_open_gate_refuses_without_smtp_and_names_the_finding(
    client, db_session, admin_headers, monkeypatch
):
    make_published_course(db_session)
    monkeypatch.setattr(settings, "email_backend", "console")
    refused = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert refused.status_code == 422
    errors = " ".join(refused.json()["errors"])
    assert "EMAIL_BACKEND" in errors
    # With the test env's dummy SMTP config the same flip succeeds.
    open_the_site(client)


# --- registration ------------------------------------------------------------


def test_registration_creates_an_unverified_participant(
    open_site, client, db_session
):
    response = register(client)
    assert response.status_code == 200
    [account] = account_rows(db_session, PAT["email"])
    assert account.role == "participant"
    assert account.display_name == "Pat Example"
    assert account.state == "NH"
    assert account.is_active is True
    assert account.must_change_password is False
    assert account.email_verified_at is None
    assert account.created_by_account_id is None
    assert outbound(db_session) == [
        ("verification", PAT["email"], "console")
    ]


def test_state_is_optional_and_validated_when_present(
    open_site, client, db_session
):
    ok = register(client, email="nostate@example.test", state="")
    assert ok.status_code == 200
    [account] = account_rows(db_session, "nostate@example.test")
    assert account.state is None

    bad = register(client, email="badstate@example.test", state="ZZ")
    assert bad.status_code == 422
    assert any('"ZZ"' in error for error in bad.json()["errors"])
    assert account_rows(db_session, "badstate@example.test") == []


def test_malformed_input_is_422_and_sends_nothing(
    open_site, client, db_session
):
    response = register(
        client, name="  ", email="not-an-email", password="short"
    )
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any("name" in error for error in errors)
    assert any("not-an-email" in error for error in errors)
    assert any("password" in error for error in errors)
    assert outbound(db_session) == []


def test_constant_response_is_byte_identical_across_all_branches(
    open_site, client, db_session, admin_account
):
    """The enumeration test: new email, taken email, and a deactivated
    account's email all get the same bytes back; only the outbound log
    knows which branch ran."""
    gone = make_account(
        db_session, "gone@example.test", "a-long-enough-password", "participant"
    )
    auth_service.deactivate(db_session, gone, actor=admin_account)

    first = register(client)
    repeat = register(client, name="Someone Else", password="another-long-password")
    deactivated = register(client, email="gone@example.test")

    assert first.status_code == repeat.status_code == deactivated.status_code == 200
    assert first.content == repeat.content == deactivated.content

    # One row for Pat (the repeat created nothing and changed nothing) …
    [account] = account_rows(db_session, PAT["email"])
    assert account.display_name == "Pat Example"
    # … and the deactivated account was neither reactivated nor doubled.
    [gone_row] = account_rows(db_session, "gone@example.test")
    assert gone_row.is_active is False
    assert gone_row.deactivated_at is not None

    assert outbound(db_session) == [
        ("verification", PAT["email"], "console"),
        ("already_registered", PAT["email"], "console"),
        ("contact_sponsor", "gone@example.test", "console"),
    ]


# --- verification ------------------------------------------------------------


def test_verify_marks_the_account_and_lets_it_log_in(
    open_site, client, db_session, caplog
):
    _, token = register_and_grab_token(client, caplog)

    # Before verification: the correct password is refused exactly like a
    # wrong one.
    right = client.post(
        LOGIN_URL, json={"email": PAT["email"], "password": PAT["password"]}
    )
    wrong = client.post(
        LOGIN_URL, json={"email": PAT["email"], "password": "not-the-password"}
    )
    assert right.status_code == wrong.status_code == 401
    assert right.content == wrong.content

    verified = client.post(VERIFY_URL, json={"token": token})
    assert verified.status_code == 200

    [account] = account_rows(db_session, PAT["email"])
    db_session.refresh(account)
    assert account.email_verified_at is not None

    after = client.post(
        LOGIN_URL, json={"email": PAT["email"], "password": PAT["password"]}
    )
    assert after.status_code == 200
    assert after.json()["role"] == "participant"


def test_used_expired_and_unknown_tokens_fail_identically(
    open_site, client, db_session, caplog
):
    _, token = register_and_grab_token(client, caplog)
    assert client.post(VERIFY_URL, json={"token": token}).status_code == 200

    reused = client.post(VERIFY_URL, json={"token": token})
    unknown = client.post(VERIFY_URL, json={"token": "no-such-token"})
    assert reused.status_code == unknown.status_code == 422
    assert reused.content == unknown.content

    # A fresh registration whose token has expired fails with those same
    # bytes.
    _, expiring = register_and_grab_token(
        client, caplog, email="late@example.test"
    )
    token_row = db_session.scalars(select(EmailVerificationToken)).all()[-1]
    token_row.expires_at = token_row.expires_at - timedelta(hours=49)
    db_session.commit()
    expired = client.post(VERIFY_URL, json={"token": expiring})
    assert expired.status_code == 422
    assert expired.content == unknown.content


def test_resend_invalidates_the_prior_token(
    open_site, client, db_session, caplog
):
    first_response, old_token = register_and_grab_token(client, caplog)

    with caplog.at_level(logging.INFO, logger="app.email"):
        resent = client.post(RESEND_URL, json={"email": PAT["email"]})
    assert resent.status_code == 200
    assert resent.content == first_response.content

    new_token = last_token_from(caplog)
    assert new_token != old_token
    assert client.post(VERIFY_URL, json={"token": old_token}).status_code == 422
    assert client.post(VERIFY_URL, json={"token": new_token}).status_code == 200


def test_resend_branches_match_registration_branches(
    open_site, client, db_session, admin_account, caplog
):
    """Unknown address: constant 200, nothing sent. Verified account: the
    already-registered email. Deactivated: the contact-sponsor email."""
    unknown = client.post(RESEND_URL, json={"email": "nobody@example.test"})
    assert unknown.status_code == 200
    assert outbound(db_session) == []

    _, token = register_and_grab_token(client, caplog)
    client.post(VERIFY_URL, json={"token": token})
    verified = client.post(RESEND_URL, json={"email": PAT["email"]})
    assert verified.content == unknown.content

    gone = make_account(
        db_session, "gone@example.test", "a-long-enough-password", "participant"
    )
    auth_service.deactivate(db_session, gone, actor=admin_account)
    deactivated = client.post(RESEND_URL, json={"email": "gone@example.test"})
    assert deactivated.content == unknown.content

    assert [kind for kind, _, _ in outbound(db_session)] == [
        "verification",
        "already_registered",
        "contact_sponsor",
    ]


# --- the admin test email ----------------------------------------------------


def test_admin_test_email_goes_through_the_backend_and_into_the_log(
    client, admin_headers, console_email, db_session
):
    response = client.post(TEST_EMAIL_URL, json={})
    assert response.status_code == 200
    assert response.json() == {
        "backend": "console",
        "recipient": ADMIN_EMAIL,
    }
    assert outbound(db_session) == [("test", ADMIN_EMAIL, "console")]


def test_admin_test_email_reports_a_refused_send(
    client, admin_headers, db_session
):
    """With the test env's dummy SMTP settings the send itself fails fast
    (smtp.invalid resolves nowhere), which is exactly what the runbook
    step needs surfaced."""
    response = client.post(TEST_EMAIL_URL, json={})
    assert response.status_code == 502
    [error] = response.json()["errors"]
    assert "refused the send" in error
    assert outbound(db_session) == []
