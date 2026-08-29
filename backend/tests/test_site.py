"""Feature 009: site mode — the logged Phase B gate on public routes.

011 added the launch gate: opening the site is refused while any 8.01
policy is unpublished, so tests that open it publish the policies first
(the refusal itself is proven in test_policies.py)."""

from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    login,
    make_account,
    publish_test_policies,
)

SITE_URL = "/api/v1/site"
SITE_MODE_URL = "/api/v1/admin/site-mode"
PUBLIC_COURSES = "/api/v1/courses"
PUBLIC_SPONSOR = "/api/v1/sponsor"

PASSWORD = "a-long-enough-password"


def open_the_site(client, note=""):
    response = client.put(SITE_MODE_URL, json={"site_mode": "open", "note": note})
    assert response.status_code == 200, response.json()
    return response


def test_default_is_coming_soon_and_public_routes_are_404(client):
    assert client.get(SITE_URL).json()["site_mode"] == "coming_soon"
    assert client.get(PUBLIC_COURSES).status_code == 404
    assert client.get(f"{PUBLIC_COURSES}/ASC606-CON").status_code == 404
    assert client.get(PUBLIC_SPONSOR).status_code == 404


def test_any_session_passes_the_closed_gate(client, db_session):
    make_account(db_session, "pat@supercpe.test", PASSWORD, "participant")
    login(client, "pat@supercpe.test", PASSWORD)
    assert client.get(PUBLIC_COURSES).status_code == 200
    assert client.get(PUBLIC_SPONSOR).status_code == 200


def test_open_site_is_public_and_the_change_is_logged(
    client, db_session, admin_account, admin_headers
):
    publish_test_policies(db_session, admin_account)
    response = open_the_site(client, note="Phase C begins.")
    [change] = response.json()
    assert change["from_mode"] == "coming_soon"
    assert change["to_mode"] == "open"
    assert change["changed_by_email"] == ADMIN_EMAIL
    assert change["note"] == "Phase C begins."
    assert change["changed_at"] is not None

    client.cookies.clear()
    assert client.get(SITE_URL).json()["site_mode"] == "open"
    assert client.get(PUBLIC_COURSES).status_code == 200
    assert client.get(PUBLIC_SPONSOR).status_code == 200

    # Flip back: closed again, and the log now has both changes.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    closed = client.put(SITE_MODE_URL, json={"site_mode": "coming_soon"})
    assert closed.status_code == 200
    client.cookies.clear()
    assert client.get(PUBLIC_COURSES).status_code == 404

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    changes = client.get(f"{SITE_MODE_URL}/changes").json()
    assert [(c["from_mode"], c["to_mode"]) for c in changes] == [
        ("open", "coming_soon"),
        ("coming_soon", "open"),
    ]


def test_setting_the_same_mode_is_refused(client, admin_headers):
    response = client.put(SITE_MODE_URL, json={"site_mode": "coming_soon"})
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "already coming_soon" in error


def test_ungated_routes_are_reachable_in_both_modes(client, db_session, admin_account):
    # Closed, no session: health, site, and login all answer (nothing 404s).
    assert client.get("/api/v1/health").status_code == 200
    assert client.get(SITE_URL).status_code == 200
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    publish_test_policies(db_session, admin_account)
    open_the_site(client)
    client.cookies.clear()
    assert client.get("/api/v1/health").status_code == 200
    assert client.get(SITE_URL).status_code == 200
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def test_site_and_auth_payloads_never_mention_the_registry(
    client, db_session, admin_account
):
    """Walks the payloads as 003 and 008 did: nothing under /api/v1/site or
    /auth may contain the words "National Registry" or a sponsor ID."""
    responses = [
        client.get(SITE_URL),
        login(client, ADMIN_EMAIL, ADMIN_PASSWORD),
        client.get("/api/v1/auth/me"),
        client.post("/api/v1/auth/logout", json={}),
    ]
    for response in responses:
        assert "National Registry" not in response.text
        assert "national_registry" not in response.text


def test_site_payload_is_only_mode_and_name(client):
    payload = client.get(SITE_URL).json()
    assert set(payload) == {"site_mode", "sponsor_name"}
