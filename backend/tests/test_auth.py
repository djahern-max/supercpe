"""Feature 009: accounts, roles, and sessions."""

import hashlib
import re
from datetime import datetime, timedelta, timezone

from fastapi.routing import APIRoute
from sqlalchemy import select

from app.constants.auth import MAX_FAILED_LOGINS, SESSION_COOKIE
from app.main import app
from app.models.account import Account, AuthSession
from app.models.review import CourseReview
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    login,
    make_account,
    publish_test_policies,
)
from tests.test_development import make_publishable_course, make_sme, publish

LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
ACCOUNTS_URL = "/api/v1/admin/accounts"

REVIEWER_EMAIL = "rae@supercpe.test"
PARTICIPANT_EMAIL = "pat@supercpe.test"
PASSWORD = "a-long-enough-password"


def cookie_headers(token):
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


def session_token(client):
    return client.cookies.get(SESSION_COOKIE)


def the_session(db, raw_token=None):
    rows = list(db.scalars(select(AuthSession)))
    if raw_token is None:
        assert len(rows) == 1
        return rows[0]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return next(r for r in rows if r.token_hash == token_hash)


# --- Login, /me, logout ------------------------------------------------------


def test_login_me_logout(client, admin_account, db_session):
    response = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert SESSION_COOKIE in response.cookies
    assert response.json()["email"] == ADMIN_EMAIL
    assert response.json()["role"] == "admin"

    me = client.get(ME_URL)
    assert me.status_code == 200
    assert me.json() == {
        "id": admin_account.id,
        "email": ADMIN_EMAIL,
        "role": "admin",
        "display_name": "",
        "must_change_password": False,
    }

    assert client.post("/api/v1/auth/logout", json={}).status_code == 204
    db_session.expire_all()
    assert the_session(db_session).revoked_at is not None
    assert client.get(ME_URL).status_code == 401


def test_login_failures_share_one_body(client, db_session, admin_account):
    inactive = make_account(db_session, "gone@supercpe.test", PASSWORD, "participant")
    inactive.is_active = False
    db_session.commit()

    responses = [
        client.post(
            LOGIN_URL, json={"email": ADMIN_EMAIL, "password": "wrong-password!"}
        ),
        client.post(
            LOGIN_URL, json={"email": "nobody@supercpe.test", "password": PASSWORD}
        ),
        client.post(
            LOGIN_URL, json={"email": "gone@supercpe.test", "password": PASSWORD}
        ),
    ]
    bodies = {r.text for r in responses}
    assert all(r.status_code == 401 for r in responses)
    assert len(bodies) == 1


def test_lockout_after_failed_logins(client, db_session, admin_account):
    for _ in range(MAX_FAILED_LOGINS):
        assert (
            client.post(
                LOGIN_URL, json={"email": ADMIN_EMAIL, "password": "wrong!"}
            ).status_code
            == 401
        )
    db_session.expire_all()
    assert admin_account.locked_until is not None

    # The correct password during the lockout is refused.
    assert (
        client.post(
            LOGIN_URL, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        ).status_code
        == 401
    )

    # Lockout over: success, and the counter is reset.
    admin_account.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    admin_account.failed_logins = 3
    db_session.commit()
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    db_session.expire_all()
    assert admin_account.failed_logins == 0
    assert admin_account.locked_until is None


def test_idle_and_absolute_expiry(client, db_session, admin_account):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.get(ME_URL).status_code == 200

    session = the_session(db_session)
    session.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=61)
    db_session.commit()
    assert client.get(ME_URL).status_code == 401

    # A fresh session, then push it past the absolute expiry even though it
    # was just seen.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.get(ME_URL).status_code == 200
    db_session.expire_all()
    fresh = the_session(db_session, session_token(client))
    fresh.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(ME_URL).status_code == 401


# --- Forced password change --------------------------------------------------


def test_must_change_password_blocks_until_changed(
    client, db_session, admin_headers
):
    created = client.post(
        ACCOUNTS_URL,
        json={"email": REVIEWER_EMAIL, "role": "reviewer"},
    )
    assert created.status_code == 201, created.json()
    initial_password = created.json()["initial_password"]

    # Two reviewer sessions; the change must kill the other one.
    login(client, REVIEWER_EMAIL, initial_password)
    other_token = session_token(client)
    login(client, REVIEWER_EMAIL, initial_password)

    assert client.get(ME_URL).json()["must_change_password"] is True
    blocked = client.get("/api/v1/review/courses")
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "must_change_password"

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": initial_password, "new_password": PASSWORD},
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
    assert client.get("/api/v1/review/courses").status_code == 200
    # The other session was revoked; this one survived.
    assert client.get(ME_URL, headers=cookie_headers(other_token)).status_code == 401


def test_short_password_refused(client, db_session, admin_headers):
    created = client.post(
        ACCOUNTS_URL, json={"email": REVIEWER_EMAIL, "role": "reviewer"}
    )
    initial_password = created.json()["initial_password"]
    login(client, REVIEWER_EMAIL, initial_password)
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": initial_password, "new_password": "short"},
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "12" in error


# --- Roles -------------------------------------------------------------------


def make_and_login(client, db_session, email, role):
    make_account(db_session, email, PASSWORD, role)
    login(client, email, PASSWORD)


def test_role_matrix(client, db_session, admin_headers, tmp_path):
    package_id = make_publishable_course(client, admin_headers, tmp_path)
    play = f"/api/v1/courses/ASC606-CON/lessons/{package_id}/play"

    make_and_login(client, db_session, PARTICIPANT_EMAIL, "participant")
    assert client.get("/api/v1/admin/courses").status_code == 403
    assert client.get("/api/v1/review/courses").status_code == 403
    assert client.get(play).status_code == 403

    make_and_login(client, db_session, REVIEWER_EMAIL, "reviewer")
    assert client.get("/api/v1/admin/courses").status_code == 403
    assert client.get("/api/v1/review/courses").status_code == 200
    assert client.get(play).status_code == 200
    assert client.get("/api/v1/courses/ASC606-CON/assessment").status_code == 200

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.get("/api/v1/admin/courses").status_code == 200
    assert client.get("/api/v1/review/courses").status_code == 200
    assert client.get(play).status_code == 200


def test_every_admin_route_is_guarded(client, db_session):
    """Walks the router table, so a new /admin route cannot ship unguarded:
    401 with no session, 403 with a participant session."""
    make_account(db_session, PARTICIPANT_EMAIL, PASSWORD, "participant")
    login(client, PARTICIPANT_EMAIL, PASSWORD)
    participant = cookie_headers(session_token(client))
    client.cookies.clear()

    admin_routes = [
        (method, re.sub(r"\{[^}]+\}", "1", route.path))
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/v1/admin")
        for method in sorted(route.methods - {"HEAD", "OPTIONS"})
    ]
    assert len(admin_routes) >= 25

    for method, path in admin_routes:
        anonymous = client.request(method, path)
        assert anonymous.status_code == 401, (method, path, anonymous.status_code)
        as_participant = client.request(method, path, headers=participant)
        assert as_participant.status_code == 403, (
            method,
            path,
            as_participant.status_code,
        )


# --- The reviewer surface ----------------------------------------------------


def test_reviewer_records_a_review_in_the_first_person(
    client, db_session, admin_account, admin_headers, tmp_path
):
    # 016: publish also requires the 8.01 item 8-10 policies.
    publish_test_policies(db_session, admin_account)
    make_publishable_course(client, admin_headers, tmp_path)
    developer = make_sme(client, admin_headers, name="Dana Developer")
    reviewer_sme = make_sme(client, admin_headers, name="Rae Reviewer")
    assert (
        client.put(
            "/api/v1/admin/courses/ASC606-CON/developer",
            json={"sme_id": developer["id"], "used_technology": True},
        ).status_code
        == 200
    )

    make_and_login(client, db_session, REVIEWER_EMAIL, "reviewer")
    listed = client.get("/api/v1/review/courses")
    assert listed.status_code == 200
    [row] = listed.json()
    assert row["course_code"] == "ASC606-CON"
    assert row["review_standing"] == "none"

    detail = client.get("/api/v1/review/courses/ASC606-CON")
    assert detail.status_code == 200
    assert {s["name"] for s in detail.json()["smes"]} == {
        "Dana Developer",
        "Rae Reviewer",
    }

    recorded = client.post(
        "/api/v1/review/courses/ASC606-CON/reviews",
        json={
            "reviewer_id": reviewer_sme["id"],
            "reviewed_at": "2026-08-29",
            "decision": "approved",
            "notes": "Accurate and current.",
        },
    )
    assert recorded.status_code == 201, recorded.json()
    assert recorded.json()["recorded_by"] == REVIEWER_EMAIL

    db_session.expire_all()
    [review] = list(db_session.scalars(select(CourseReview)))
    reviewer_account = db_session.scalar(
        select(Account).where(Account.email == REVIEWER_EMAIL)
    )
    assert review.recorded_by_account_id == reviewer_account.id
    assert review.recorded_by == REVIEWER_EMAIL

    # The 008 history shows it, standing computed as before.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    [listed] = client.get("/api/v1/admin/courses/ASC606-CON/reviews").json()
    assert listed["recorded_by"] == REVIEWER_EMAIL
    assert listed["is_current"] is True
    response = publish(client, {}, "ASC606-CON")
    assert response.status_code == 200, response.json()


def test_reviewer_naming_the_developer_still_blocks_publish(
    client, db_session, admin_headers, tmp_path
):
    make_publishable_course(client, admin_headers, tmp_path)
    developer = make_sme(client, admin_headers, name="Dana Developer")
    assert (
        client.put(
            "/api/v1/admin/courses/ASC606-CON/developer",
            json={"sme_id": developer["id"], "used_technology": True},
        ).status_code
        == 200
    )

    make_and_login(client, db_session, REVIEWER_EMAIL, "reviewer")
    assert (
        client.post(
            "/api/v1/review/courses/ASC606-CON/reviews",
            json={
                "reviewer_id": developer["id"],
                "reviewed_at": "2026-08-29",
                "decision": "approved",
            },
        ).status_code
        == 201
    )

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = publish(client, {}, "ASC606-CON")
    assert response.status_code == 422
    assert any(
        "other than those who developed" in e for e in response.json()["errors"]
    )


# --- Account management ------------------------------------------------------


def test_admin_cannot_deactivate_or_demote_self(client, admin_account, admin_headers):
    response = client.post(f"{ACCOUNTS_URL}/{admin_account.id}/deactivate")
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "cannot deactivate their own account" in error

    response = client.put(
        f"{ACCOUNTS_URL}/{admin_account.id}/role", json={"role": "reviewer"}
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "cannot demote their own account" in error


def test_deactivation_revokes_sessions_and_keeps_the_review(
    client, db_session, admin_headers, tmp_path
):
    make_publishable_course(client, admin_headers, tmp_path)
    sme = make_sme(client, admin_headers, name="Rae Reviewer")
    admin_token = session_token(client)

    make_and_login(client, db_session, REVIEWER_EMAIL, "reviewer")
    reviewer_token = session_token(client)
    assert (
        client.post(
            "/api/v1/review/courses/ASC606-CON/reviews",
            json={
                "reviewer_id": sme["id"],
                "reviewed_at": "2026-08-29",
                "decision": "approved",
            },
        ).status_code
        == 201
    )

    client.cookies.clear()
    reviewer_account = db_session.scalar(
        select(Account).where(Account.email == REVIEWER_EMAIL)
    )
    deactivated = client.post(
        f"{ACCOUNTS_URL}/{reviewer_account.id}/deactivate",
        headers=cookie_headers(admin_token),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # The next request on the reviewer's old cookie is dead.
    assert (
        client.get(ME_URL, headers=cookie_headers(reviewer_token)).status_code
        == 401
    )
    # The review they recorded is still in the history.
    [review] = client.get(
        "/api/v1/admin/courses/ASC606-CON/reviews",
        headers=cookie_headers(admin_token),
    ).json()
    assert review["recorded_by"] == REVIEWER_EMAIL


def test_initial_password_appears_exactly_once(client, db_session, admin_headers):
    created = client.post(
        ACCOUNTS_URL, json={"email": REVIEWER_EMAIL, "role": "reviewer"}
    )
    assert created.status_code == 201
    initial_password = created.json()["initial_password"]
    assert len(initial_password) >= 12

    account = db_session.scalar(
        select(Account).where(Account.email == REVIEWER_EMAIL)
    )
    assert initial_password not in account.password_hash
    assert initial_password not in client.get(ACCOUNTS_URL).text
    # And it works, once, for a first login.
    login(client, REVIEWER_EMAIL, initial_password)


def test_duplicate_email_refused(client, admin_headers):
    assert (
        client.post(
            ACCOUNTS_URL, json={"email": REVIEWER_EMAIL, "role": "reviewer"}
        ).status_code
        == 201
    )
    response = client.post(
        ACCOUNTS_URL, json={"email": REVIEWER_EMAIL.upper(), "role": "participant"}
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "already exists" in error


def test_reactivate_restores_login(client, db_session, admin_headers):
    account = make_account(db_session, PARTICIPANT_EMAIL, PASSWORD, "participant")
    assert (
        client.post(f"{ACCOUNTS_URL}/{account.id}/deactivate").status_code == 200
    )
    assert (
        client.post(
            LOGIN_URL, json={"email": PARTICIPANT_EMAIL, "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(f"{ACCOUNTS_URL}/{account.id}/reactivate").status_code == 200
    )
    login(client, PARTICIPANT_EMAIL, PASSWORD)
