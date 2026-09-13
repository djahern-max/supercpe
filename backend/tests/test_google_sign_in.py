"""Feature 030: sign in with Google.

The boundary (`services.google_identity.verify`) is stubbed the way 018
stubs `stripe_gateway`: a credential string maps to a GoogleIdentity or
to the error the boundary would raise; nothing touches the network. The
compliance-shaped tests are the constant-response ones — every refusal
byte-identical, whatever the reason — and the password-login refusal on
an account that has no password.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.account import Account, AuthSession
from app.services import auth as auth_service
from app.services import google_identity
from app.services.google_identity import GoogleIdentity, GoogleIdentityError
from tests.conftest import login, make_account
from tests.test_enrollments import make_published_course
from tests.test_site import open_the_site

GOOGLE_URL = "/api/v1/auth/google"
CONFIG_URL = "/api/v1/auth/google/config"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
CHANGE_PASSWORD_URL = "/api/v1/auth/change-password"

CLIENT_ID = "1234567890-test.apps.googleusercontent.com"
PASSWORD = "a-long-enough-password"
REFUSED = {"detail": auth_service.GOOGLE_SIGN_IN_FAILED}


def identity(sub="sub-pat", email="Pat@Example.test", verified=True, name="Pat Example"):
    return GoogleIdentity(sub=sub, email=email, email_verified=verified, name=name)


def stub_google_tokens(monkeypatch):
    """The stubbed boundary: credential -> GoogleIdentity, or -> the
    GoogleIdentityError the real verifier would raise. Unknown credentials
    are bad tokens. The client id is configured unless a test unsets it.
    Shared with test_google_preview.py (030a)."""
    table = {}

    def fake_verify(credential):
        if not settings.google_configured:
            raise GoogleIdentityError("GOOGLE_CLIENT_ID is not configured")
        outcome = table.get(credential)
        if outcome is None:
            raise GoogleIdentityError("Signature verification failed")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(google_identity, "verify", fake_verify)
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    return table


@pytest.fixture
def tokens(monkeypatch):
    return stub_google_tokens(monkeypatch)


@pytest.fixture
def open_site(client, db_session, admin_headers, console_email):
    """The site open and the admin logged out — the state a member of the
    public signs in from."""
    make_published_course(db_session)
    open_the_site(client)
    client.cookies.clear()


def google(client, credential):
    return client.post(GOOGLE_URL, json={"credential": credential})


def account_rows(db_session, email):
    return list(
        db_session.scalars(select(Account).where(Account.email == email))
    )


# --- Config --------------------------------------------------------------------


def test_config_carries_the_client_id_and_nothing_else(client, open_site, tokens):
    response = client.get(CONFIG_URL)
    assert response.status_code == 200
    assert response.json() == {"client_id": CLIENT_ID}


def test_config_is_null_when_unset(client, open_site, tokens, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    assert client.get(CONFIG_URL).json() == {"client_id": None}


def test_both_routes_404_anonymously_in_coming_soon(client, tokens):
    assert client.get(CONFIG_URL).status_code == 404
    assert google(client, "anything").status_code == 404


def test_both_routes_answer_with_a_session_in_coming_soon(
    client, db_session, tokens
):
    make_account(db_session, "pat@supercpe.test", PASSWORD, "participant")
    login(client, "pat@supercpe.test", PASSWORD)
    assert client.get(CONFIG_URL).status_code == 200
    # A bad token with a session: the constant refusal, not the gate's 404.
    assert google(client, "bad").status_code == 401


# --- The three outcomes ----------------------------------------------------------


def test_new_email_creates_a_participant_with_no_password(
    client, db_session, open_site, tokens
):
    tokens["t"] = identity()
    response = google(client, "t")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["email"] == "pat@example.test"
    assert body["role"] == "participant"
    assert body["display_name"] == "Pat Example"
    assert body["must_change_password"] is False
    assert body["signin_methods"] == ["google"]
    assert "supercpe_session" in response.cookies

    (account,) = account_rows(db_session, "pat@example.test")
    assert account.password_hash is None
    assert account.google_sub == "sub-pat"
    assert account.email_verified_at is not None
    assert account.created_by_account_id is None
    sessions = list(
        db_session.scalars(
            select(AuthSession).where(AuthSession.account_id == account.id)
        )
    )
    assert len(sessions) == 1

    # The session is real: /me answers through the cookie.
    me = client.get(ME_URL)
    assert me.status_code == 200
    assert me.json()["id"] == account.id


def test_response_shape_is_identical_to_password_login(
    client, db_session, open_site, tokens
):
    make_account(db_session, "pw@example.test", PASSWORD, "participant")
    password_body = login(client, "pw@example.test", PASSWORD).json()
    client.cookies.clear()
    tokens["t"] = identity()
    google_body = google(client, "t").json()
    assert set(google_body) == set(password_body)
    assert password_body["signin_methods"] == ["password"]


def test_existing_participant_is_linked_once_and_then_matched_by_sub(
    client, db_session, open_site, tokens
):
    existing = make_account(db_session, "pat@example.test", PASSWORD, "participant")
    accounts_before = len(list(db_session.scalars(select(Account))))
    tokens["first"] = identity(sub="sub-pat", email="PAT@example.test")
    response = google(client, "first")
    assert response.status_code == 200, response.json()
    assert response.json()["id"] == existing.id
    assert response.json()["signin_methods"] == ["password", "google"]
    db_session.refresh(existing)
    assert existing.google_sub == "sub-pat"
    assert existing.password_hash is not None

    # Google later reports a different email for the same sub: still the
    # same account, matched by sub; no second row, email unchanged.
    client.cookies.clear()
    tokens["renamed"] = identity(sub="sub-pat", email="pat.new@example.test")
    response = google(client, "renamed")
    assert response.status_code == 200
    assert response.json()["id"] == existing.id
    assert account_rows(db_session, "pat.new@example.test") == []
    db_session.refresh(existing)
    assert existing.email == "pat@example.test"
    assert existing.google_sub == "sub-pat"
    assert len(list(db_session.scalars(select(Account)))) == accounts_before


def test_linking_marks_an_unverified_registration_verified(
    client, db_session, open_site, tokens
):
    """Google's verification satisfies 017's requirement: an account that
    registered with a password but never clicked the link is verified by
    its first Google sign-in, and password login then works too."""
    unverified = auth_service.create_account(
        db_session,
        "pat@example.test",
        "participant",
        PASSWORD,
        created_by=None,
        must_change_password=False,
        email_verified=False,
    )
    assert client.post(
        LOGIN_URL, json={"email": "pat@example.test", "password": PASSWORD}
    ).status_code == 401
    tokens["t"] = identity()
    assert google(client, "t").status_code == 200
    db_session.refresh(unverified)
    assert unverified.email_verified_at is not None
    client.cookies.clear()
    login(client, "pat@example.test", PASSWORD)


# --- Every refusal is one body -----------------------------------------------------


def test_every_refusal_is_the_same_constant_401(
    client, db_session, open_site, tokens
):
    deactivated = make_account(
        db_session, "gone@example.test", PASSWORD, "participant"
    )
    deactivated.is_active = False
    db_session.commit()
    make_account(db_session, "root@example.test", PASSWORD, "admin")
    make_account(db_session, "rae@example.test", PASSWORD, "reviewer")
    linked = make_account(db_session, "linked@example.test", PASSWORD, "participant")
    linked.google_sub = "sub-someone-else"
    db_session.commit()
    before = {
        a.email: (a.google_sub, a.email_verified_at, a.password_hash, a.role)
        for a in db_session.scalars(select(Account))
    }
    sessions_before = len(list(db_session.scalars(select(AuthSession))))

    tokens["deactivated"] = identity(sub="s1", email="gone@example.test")
    tokens["admin"] = identity(sub="s2", email="root@example.test")
    tokens["reviewer"] = identity(sub="s3", email="rae@example.test")
    tokens["unverified"] = identity(sub="s4", email="new@example.test", verified=False)
    tokens["expired"] = GoogleIdentityError("Signature has expired")
    tokens["audience"] = GoogleIdentityError("Audience doesn't match")
    tokens["other-sub"] = identity(sub="s5", email="linked@example.test")
    cases = [
        "deactivated",
        "admin",
        "reviewer",
        "unverified",
        "expired",
        "audience",
        "other-sub",
        "not-a-token-at-all",
    ]
    answers = {case: google(client, case) for case in cases}
    for case, response in answers.items():
        assert response.status_code == 401, case
        assert "supercpe_session" not in response.cookies, case
    bodies = {response.content for response in answers.values()}
    assert len(bodies) == 1
    assert answers["admin"].json() == REFUSED

    # Nothing was created or changed by any refusal.
    db_session.expire_all()
    after = {
        a.email: (a.google_sub, a.email_verified_at, a.password_hash, a.role)
        for a in db_session.scalars(select(Account))
    }
    assert after == before
    assert account_rows(db_session, "new@example.test") == []
    assert len(list(db_session.scalars(select(AuthSession)))) == sessions_before


def test_unset_client_id_refuses_with_the_constant_401_not_404(
    client, open_site, tokens, monkeypatch
):
    monkeypatch.setattr(settings, "google_client_id", "")
    tokens["t"] = identity()
    response = google(client, "t")
    assert response.status_code == 401
    assert response.json() == REFUSED


# --- Password login on an account with no password ------------------------------


def test_password_login_on_a_google_only_account_is_the_wrong_password_answer(
    client, db_session, open_site, tokens
):
    tokens["t"] = identity()
    assert google(client, "t").status_code == 200
    client.cookies.clear()
    make_account(db_session, "pw@example.test", PASSWORD, "participant")

    wrong_password = client.post(
        LOGIN_URL, json={"email": "pw@example.test", "password": "not-it-at-all"}
    )
    no_password = client.post(
        LOGIN_URL, json={"email": "pat@example.test", "password": PASSWORD}
    )
    assert wrong_password.status_code == no_password.status_code == 401
    assert wrong_password.content == no_password.content
    assert no_password.json() == {"detail": auth_service.LOGIN_FAILED}


def test_change_password_on_a_google_only_account_is_refused_cleanly(
    client, db_session, open_site, tokens
):
    """No current password exists to give, so the 009 route refuses with
    its own message rather than crashing on the null hash."""
    tokens["t"] = identity()
    assert google(client, "t").status_code == 200
    response = client.post(
        CHANGE_PASSWORD_URL,
        json={"current_password": "", "new_password": "another-long-password"},
    )
    assert response.status_code == 422
    assert response.json() == {"errors": ["The current password is incorrect"]}
    (account,) = account_rows(db_session, "pat@example.test")
    db_session.refresh(account)
    assert account.password_hash is None


def test_a_password_set_later_makes_both_methods_work(
    client, db_session, open_site, tokens
):
    """What a reset flow would store — a hash on the row — is enough: the
    account then has both methods. (No reset flow exists yet; see the
    030 changelog.)"""
    tokens["t"] = identity()
    assert google(client, "t").status_code == 200
    client.cookies.clear()
    (account,) = account_rows(db_session, "pat@example.test")
    account.password_hash = auth_service._hasher.hash(PASSWORD)
    db_session.commit()

    body = login(client, "pat@example.test", PASSWORD).json()
    assert body["signin_methods"] == ["password", "google"]
    client.cookies.clear()
    assert google(client, "t").json()["signin_methods"] == ["password", "google"]


# --- Data model ------------------------------------------------------------------


def test_two_accounts_cannot_share_a_google_sub(db_session):
    make_account(db_session, "a@example.test", PASSWORD, "participant")
    make_account(db_session, "b@example.test", PASSWORD, "participant")
    a, b = db_session.scalars(select(Account).order_by(Account.id))
    a.google_sub = "sub-shared"
    db_session.commit()
    b.google_sub = "sub-shared"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_signin_methods_are_derived_from_the_row():
    assert auth_service.signin_methods(Account(password_hash="x")) == ["password"]
    assert auth_service.signin_methods(Account(google_sub="s")) == ["google"]
    assert auth_service.signin_methods(Account(password_hash="x", google_sub="s")) == [
        "password",
        "google",
    ]
    assert auth_service.signin_methods(Account()) == []
