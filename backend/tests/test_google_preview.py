"""Feature 030a: Google sign-in preview on a closed site.

The 009 gate refuses anonymous requests on a coming_soon site with one
bare 404. 030a lets exactly the addresses the operator names in
GOOGLE_PREVIEW_EMAILS past it on the two Google routes — and nobody
else: every other outcome is that same 404, byte for byte, and nothing
is created or changed before the allowlist check passes. With the list
unset, every behavior here is 030's. The Google boundary is stubbed as
test_google_sign_in.py stubs it.
"""

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.account import Account, AuthSession
from app.routers import auth as auth_router
from app.services import auth as auth_service
from app.services.google_identity import GoogleIdentityError
from tests.conftest import ADMIN_PASSWORD, login, make_account
from tests.test_enrollments import make_published_course
from tests.test_google_sign_in import (
    CLIENT_ID,
    CONFIG_URL,
    GOOGLE_URL,
    REFUSED,
    account_rows,
    google,
    identity,
    stub_google_tokens,
)
from tests.test_site import GOOGLE_PREVIEW_ROUTES, INTENTIONALLY_PUBLIC, open_the_site

PASSWORD = "a-long-enough-password"
LISTED = "dane@example.test"
# A 030-era snapshot of the gate's answer: what GET /api/v1/courses gives
# an anonymous request while coming_soon, and what both Google routes
# gave before this feature.
GATE_404 = b'{"detail":"Not found"}'


@pytest.fixture
def tokens(monkeypatch):
    return stub_google_tokens(monkeypatch)


@pytest.fixture
def preview_list(monkeypatch):
    """The operator's list: one address, mixed case and padded, so the
    case-folding and stripping are exercised on every listed sign-in."""
    monkeypatch.setattr(settings, "google_preview_emails", " Dane@Example.test ,")


def snapshot(db_session):
    db_session.expire_all()
    return (
        {
            a.email: (a.google_sub, a.email_verified_at, a.password_hash, a.role)
            for a in db_session.scalars(select(Account))
        },
        len(list(db_session.scalars(select(AuthSession)))),
    )


def assert_gate_404(client, response):
    assert response.status_code == 404
    assert response.content == GATE_404
    # The same bytes the gate gives on a route this feature never touched.
    gated = client.get("/api/v1/courses")
    assert gated.status_code == 404
    assert gated.content == response.content


# --- List empty: byte-identical to 030 ------------------------------------------


def test_empty_list_both_routes_give_the_gate_404_and_touch_nothing(
    client, db_session, tokens
):
    assert settings.google_preview_email_set == frozenset()
    tokens["t"] = identity(email=LISTED)
    before = snapshot(db_session)

    assert_gate_404(client, client.get(CONFIG_URL))
    assert_gate_404(client, google(client, "t"))
    # A malformed body meets the gate before the body is parsed, as in
    # 030 — never a 422 that says the route exists.
    assert_gate_404(client, client.post(GOOGLE_URL, json={}))

    assert snapshot(db_session) == before
    assert account_rows(db_session, LISTED) == []


# --- A listed address: coming-soon behaves exactly as open ----------------------


def test_listed_email_signs_in_while_coming_soon_exactly_as_at_open(
    client, db_session, admin_account, preview_list, tokens, console_email
):
    assert client.get(CONFIG_URL).status_code == 200
    assert client.get(CONFIG_URL).json() == {"client_id": CLIENT_ID}

    tokens["t"] = identity(sub="sub-dane", email="dane@example.test", name="Dane")
    closed = google(client, "t")
    assert closed.status_code == 200, closed.json()
    assert "supercpe_session" in closed.cookies
    (account,) = account_rows(db_session, LISTED)
    assert account.role == "participant"
    assert account.password_hash is None
    assert account.google_sub == "sub-dane"
    assert account.email_verified_at is not None
    assert client.get("/api/v1/auth/me").json()["id"] == account.id

    # The same token once the site is open: the same account, and the
    # same body byte for byte — nothing in the response forks on mode.
    client.cookies.clear()
    login(client, admin_account.email, ADMIN_PASSWORD)
    make_published_course(db_session)
    open_the_site(client)
    client.cookies.clear()
    opened = google(client, "t")
    assert opened.status_code == 200
    assert opened.content == closed.content
    assert set(opened.json()) == {
        "id",
        "email",
        "role",
        "display_name",
        "must_change_password",
        "subscription_current",
        "signin_methods",
    }


def test_case_folding_matches_the_stored_lower_case_email(
    client, preview_list, tokens
):
    assert settings.google_preview_email_set == frozenset({LISTED})
    tokens["upper"] = identity(sub="s", email="DANE@EXAMPLE.TEST")
    assert google(client, "upper").status_code == 200


# --- Everyone not listed: the gate's 404, and nothing written -------------------


def test_every_unlisted_outcome_is_the_gate_404_and_writes_nothing(
    client, db_session, preview_list, tokens, monkeypatch
):
    make_account(db_session, "pat@example.test", PASSWORD, "participant")
    before = snapshot(db_session)

    def never(db, credential):  # pragma: no cover — the assertion is the point
        raise AssertionError("sign_in_with_google ran before the allowlist passed")

    monkeypatch.setattr(auth_router.auth_service, "sign_in_with_google", never)

    tokens["unlisted-new"] = identity(sub="s1", email="new@example.test")
    tokens["unlisted-existing"] = identity(sub="s2", email="pat@example.test")
    tokens["unverified"] = identity(sub="s3", email=LISTED, verified=False)
    tokens["expired"] = GoogleIdentityError("Signature has expired")
    tokens["audience"] = GoogleIdentityError("Audience doesn't match")
    cases = [
        "unlisted-new",
        "unlisted-existing",
        "unverified",
        "expired",
        "audience",
        "not-a-token-at-all",
    ]
    answers = {case: google(client, case) for case in cases}
    for case, response in answers.items():
        assert response.status_code == 404, case
        assert "supercpe_session" not in response.cookies, case
        assert_gate_404(client, response)
    assert {response.content for response in answers.values()} == {GATE_404}

    assert snapshot(db_session) == before
    assert account_rows(db_session, "new@example.test") == []


def test_listed_email_on_a_refused_account_gets_the_constant_401_not_404(
    client, db_session, tokens, monkeypatch
):
    """Once listed, refusals look exactly as they do at open: the admin's
    own address on the list is refused by the service, not the gate."""
    monkeypatch.setattr(
        settings,
        "google_preview_emails",
        "root@example.test,rae@example.test,gone@example.test",
    )
    make_account(db_session, "root@example.test", PASSWORD, "admin")
    make_account(db_session, "rae@example.test", PASSWORD, "reviewer")
    gone = make_account(db_session, "gone@example.test", PASSWORD, "participant")
    gone.is_active = False
    db_session.commit()
    before = snapshot(db_session)

    tokens["admin"] = identity(sub="s1", email="root@example.test")
    tokens["reviewer"] = identity(sub="s2", email="rae@example.test")
    tokens["deactivated"] = identity(sub="s3", email="gone@example.test")
    for case in ("admin", "reviewer", "deactivated"):
        response = google(client, case)
        assert response.status_code == 401, case
        assert response.json() == REFUSED, case
    assert snapshot(db_session) == before


# --- Open: the list is inert -------------------------------------------------------


def test_at_open_the_list_changes_no_answer(
    client, db_session, admin_headers, console_email, tokens, monkeypatch
):
    make_published_course(db_session)
    open_the_site(client)
    client.cookies.clear()
    make_account(db_session, "root@example.test", PASSWORD, "admin")
    tokens["new"] = identity(sub="s1", email="new@example.test")
    tokens["admin"] = identity(sub="s2", email="root@example.test")
    tokens["unverified"] = identity(sub="s3", email="x@example.test", verified=False)
    cases = ["new", "admin", "unverified", "bad-token"]

    def run():
        answers = {"config": client.get(CONFIG_URL)}
        for case in cases:
            client.cookies.clear()
            answers[case] = google(client, case)
        client.cookies.clear()
        return {k: (r.status_code, r.content) for k, r in answers.items()}

    monkeypatch.setattr(settings, "google_preview_emails", "")
    with_empty = run()
    monkeypatch.setattr(settings, "google_preview_emails", "new@example.test,root@example.test")
    with_list = run()
    assert with_empty == with_list
    assert with_empty["config"][0] == 200
    assert with_empty["new"][0] == 200
    assert with_empty["admin"][0] == 401
    assert with_empty["unverified"][0] == 401
    assert with_empty["bad-token"][0] == 401


# --- A session: as before, whatever the list says -------------------------------


def test_with_a_session_in_coming_soon_both_routes_answer_regardless_of_list(
    client, db_session, tokens, monkeypatch
):
    make_account(db_session, "pat@supercpe.test", PASSWORD, "participant")
    login(client, "pat@supercpe.test", PASSWORD)
    for value in ("", LISTED):
        monkeypatch.setattr(settings, "google_preview_emails", value)
        assert client.get(CONFIG_URL).json() == {"client_id": CLIENT_ID}
        bad = google(client, "bad")
        assert bad.status_code == 401
        assert bad.json() == REFUSED


# --- The router walk's list -------------------------------------------------------


def test_the_two_google_routes_are_the_only_preview_routes():
    assert GOOGLE_PREVIEW_ROUTES == {
        ("GET", "/api/v1/auth/google/config"),
        ("POST", "/api/v1/auth/google"),
    }
    assert GOOGLE_PREVIEW_ROUTES <= INTENTIONALLY_PUBLIC


def test_the_preview_check_uses_the_shared_derivation():
    """`_preview_listed` lowers the token's email the way accounts.email
    is stored, so the env value and the token match however either is
    cased; an empty list answers False without touching the boundary."""
    assert auth_service.signin_methods(Account(google_sub="s")) == ["google"]
    assert settings.google_preview_email_set == frozenset()
    assert auth_router._preview_listed("anything") is False
