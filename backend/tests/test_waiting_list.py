"""Feature 015: the coming-soon landing payload and the waiting list.

The compliance-shaped tests are the payload-key assertion (the landing
response has no field a course fact could ride in — 8.01's partial
disclosure is worse than none) and the Registry-claim walk ("National
Registry" absent while `may_claim_registry` is false — the first public
surface under 003's rule)."""

from sqlalchemy import select

from app.models.waiting_list import WaitingListEntry
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, publish_test_policies
from tests.test_site import open_the_site

LANDING_URL = "/api/v1/landing"
SIGNUP_URL = "/api/v1/waiting-list"
ADMIN_URL = "/api/v1/admin/waiting-list"
EXPORT_URL = "/api/v1/admin/waiting-list/export.csv"

PAT = {
    "name": "Pat Example",
    "email": "pat@example.test",
    "state": "NH",
    "firm": "Example & Co",
}


def sign_up(client, **overrides):
    return client.post(SIGNUP_URL, json={**PAT, **overrides})


def all_rows(db_session):
    return list(db_session.scalars(select(WaitingListEntry)))


# --- The landing payload -----------------------------------------------------


def test_landing_payload_has_no_room_for_course_facts(client):
    response = client.get(LANDING_URL)
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "sponsor_name",
        "may_claim_registry",
        "policies_published",
    }
    assert payload["may_claim_registry"] is False
    assert payload["policies_published"] is False


def test_landing_never_mentions_the_registry_while_unclaimable(client):
    """003's rule on its first public surface: while may_claim_registry
    is false, the rendered landing response carries no Registry words."""
    response = client.get(LANDING_URL)
    assert response.json()["may_claim_registry"] is False
    assert "National Registry" not in response.text
    assert "national_registry" not in response.text


def test_landing_reports_published_policies(client, db_session, admin_account):
    publish_test_policies(db_session, admin_account)
    assert client.get(LANDING_URL).json()["policies_published"] is True


# --- Signup ------------------------------------------------------------------


def test_signup_creates_one_row(client, db_session):
    response = sign_up(client)
    assert response.status_code == 200
    [row] = all_rows(db_session)
    assert row.name == "Pat Example"
    assert row.email == "pat@example.test"
    assert row.state == "NH"
    assert row.firm == "Example & Co"
    assert row.source == "coming_soon"
    assert row.removed_at is None


def test_repeat_email_is_idempotent(client, db_session):
    first = sign_up(client)
    created_at = all_rows(db_session)[0].created_at
    # Case and whitespace differences still mean the same person.
    repeat = sign_up(client, email="  Pat@Example.TEST ", firm="")
    assert repeat.status_code == 200
    assert repeat.json() == first.json()
    [row] = all_rows(db_session)
    assert row.created_at == created_at
    # A repeat moves nothing — the original details stand.
    assert row.firm == "Example & Co"


def test_bad_state_and_blanks_are_422_in_the_standard_shape(client, db_session):
    response = sign_up(client, name="  ", email="not-an-email", state="ZZ")
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any("name" in error for error in errors)
    assert any("not-an-email" in error for error in errors)
    assert any('"ZZ"' in error for error in errors)
    assert all_rows(db_session) == []


def test_honeypot_answers_200_and_stores_nothing(client, db_session):
    real = sign_up(client)
    tripped = sign_up(
        client, email="bot@example.test", website="https://spam.example"
    )
    assert tripped.status_code == 200
    # Same body as a real signup, so a bot learns nothing.
    assert tripped.json() == real.json()
    [row] = all_rows(db_session)
    assert row.email == "pat@example.test"


def test_signup_against_a_removed_row_re_adds(client, db_session, admin_headers):
    sign_up(client)
    [row] = all_rows(db_session)
    created_at = row.created_at
    removed = client.post(
        f"{ADMIN_URL}/{row.id}/remove", json={"reason": "asked by email"}
    )
    assert removed.status_code == 200
    assert removed.json()["total"] == 0

    client.cookies.clear()
    response = sign_up(client, firm="New Firm")
    assert response.status_code == 200
    [row] = all_rows(db_session)
    db_session.refresh(row)
    assert row.removed_at is None
    assert row.removed_reason is None
    assert row.firm == "New Firm"
    assert row.created_at == created_at


# --- Both public routes exist only while coming_soon -------------------------


def test_open_site_404s_both_routes(client, db_session, admin_account):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    publish_test_policies(db_session, admin_account)
    open_the_site(client)
    client.cookies.clear()
    assert client.get(LANDING_URL).status_code == 404
    assert sign_up(client).status_code == 404
    # Even a session does not reopen them: the list is closed for good.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.get(LANDING_URL).status_code == 404
    # The admin surface still works — reading what was collected is fine.
    assert client.get(ADMIN_URL).status_code == 200


# --- Admin surface -----------------------------------------------------------


def test_admin_listing_counts_and_excludes_removed(client, db_session, admin_headers):
    client.cookies.clear()
    sign_up(client)
    sign_up(client, name="Ricky Revoked", email="ricky@example.test", state="VT")
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    listing = client.get(ADMIN_URL).json()
    assert listing["total"] == 2
    ricky = next(e for e in listing["entries"] if e["email"] == "ricky@example.test")
    assert set(ricky) == {
        "id", "name", "email", "state", "firm", "created_at", "source",
    }

    after = client.post(f"{ADMIN_URL}/{ricky['id']}/remove", json={}).json()
    assert after["total"] == 1
    assert [e["email"] for e in after["entries"]] == ["pat@example.test"]

    assert (
        client.post(f"{ADMIN_URL}/999/remove", json={}).status_code == 404
    )


def test_csv_export_is_the_active_list_with_iso_timestamps(
    client, db_session, admin_headers
):
    client.cookies.clear()
    sign_up(client, firm="")
    sign_up(client, name="Ricky Revoked", email="ricky@example.test", state="VT")
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    ricky = next(
        e
        for e in client.get(ADMIN_URL).json()["entries"]
        if e["email"] == "ricky@example.test"
    )
    client.post(f"{ADMIN_URL}/{ricky['id']}/remove", json={})

    response = client.get(EXPORT_URL)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    header, *rows = response.content.decode("utf-8").strip().splitlines()
    assert header == "name,email,state,firm,signed_up_at,source"
    [pat] = rows
    name, email, state, firm, signed_up_at, source = pat.split(",")
    assert (name, email, state, firm, source) == (
        "Pat Example", "pat@example.test", "NH", "", "coming_soon",
    )
    # ISO-8601 with timezone, e.g. 2026-08-30T12:34:56.789012+00:00
    assert signed_up_at.count("-") >= 2 and "T" in signed_up_at
    assert signed_up_at.endswith("+00:00")
