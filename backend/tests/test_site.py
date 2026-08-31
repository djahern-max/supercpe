"""Feature 009: site mode — the logged Phase B gate on public routes.

011 added the launch gate: opening the site is refused while any 8.01
policy is unpublished; 016 extended it to also require a published course
that discloses completely. Tests that open the site call
`make_published_course` first, which satisfies both (the refusals
themselves are proven in test_policies.py and test_disclosure.py). 015
added the router-table walk with its intentionally-public list."""

import re

from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    login,
    make_account,
)
from tests.test_enrollments import make_published_course

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
    make_published_course(db_session)
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

    make_published_course(db_session)
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


# Routes that answer an anonymous request while the site is coming_soon,
# on purpose. Adding a route here is a deliberate act with a feature
# number beside it, so the walk below never has to be weakened.
INTENTIONALLY_PUBLIC = {
    # 009/012: how the frontend learns the mode, how anyone signs in or
    # out, and what the uptime monitor watches.
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/site"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    # 015: the two coming_soon carve-outs — the landing payload and the
    # waiting-list signup. Both 404 again once the site opens.
    ("GET", "/api/v1/landing"),
    ("POST", "/api/v1/waiting-list"),
}


def test_router_walk_closed_site_hides_everything_not_intentionally_public(
    client,
):
    """Walks the whole router table anonymously while coming_soon: every
    route must answer 404 (the site gate, or a miss like /media) or 401
    (a login wall) unless it is in INTENTIONALLY_PUBLIC — so an unguarded
    new route fails here by name."""
    routes = [
        (method, re.sub(r"\{[^}]+\}", "1", route.path))
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"})
    ]
    assert len(routes) >= 60

    for method, path in routes:
        # An empty JSON body, so the auth routes' Content-Type check
        # (415) does not stand in for the auth answer being asserted.
        body = {} if method in ("POST", "PUT", "PATCH") else None
        response = client.request(method, path, json=body)
        if (method, path) in INTENTIONALLY_PUBLIC:
            assert response.status_code != 404, (method, path)
        else:
            assert response.status_code in (401, 404), (
                method,
                path,
                response.status_code,
            )
