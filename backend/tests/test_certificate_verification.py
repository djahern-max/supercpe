"""Feature 019: public certificate verification.

The load-bearing tests: the response is assembled from the snapshot only
(a mutated course cannot move it), unknown and malformed codes answer
identically (no existence oracle), the route obeys the site gate like
every Phase C route (the 015 walk's allowlist is unchanged), and 017's
`/verify` namespace is untouched.
"""

from pathlib import Path

from app.services import registration as registration_service
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_completion import make_completed
from tests.test_site import open_the_site

VERIFY = "/api/v1/certificates/verify"


def test_real_code_answers_from_the_snapshot_only(
    client, db_session, admin_account, admin_headers
):
    course, enrollment, _ = make_completed(db_session)
    code = enrollment.completion.verification_token
    open_the_site(client)
    client.cookies.clear()

    response = client.get(f"{VERIFY}/{code}")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "valid": True,
        "participant_name": "Pat Smith",
        "course_title": "Course GOLD",
        "field_of_study": "Accounting",
        "credit": "0.4",
        "completed_at": enrollment.completion.completed_at.date().isoformat(),
        "sponsor_name": "superCPE",
        "program_type": "Self study",
    }

    # The live course moves; the certificate does not.
    course.title = "Renamed Course"
    course.field_of_study = "Taxes"
    db_session.commit()
    assert client.get(f"{VERIFY}/{code}").json() == body


def test_unknown_and_malformed_codes_answer_identically(
    client, db_session, admin_account, admin_headers
):
    make_completed(db_session)
    open_the_site(client)
    client.cookies.clear()

    unknown = client.get(f"{VERIFY}/{'0' * 64}")
    malformed = client.get(f"{VERIFY}/not-a-code-at-all")
    assert unknown.status_code == malformed.status_code == 404
    assert unknown.json() == malformed.json() == {"detail": "Not found"}


def test_mode_matrix(client, db_session, admin_account, admin_headers):
    """404 anonymously in coming_soon — byte-identical to an unknown code
    at open, so the closed site reveals nothing — public at open, and a
    session passes the closed gate like everywhere else."""
    _, enrollment, _ = make_completed(db_session)
    code = enrollment.completion.verification_token

    # admin_headers logged the admin in; the session passes the gate.
    assert client.get(f"{VERIFY}/{code}").status_code == 200

    client.cookies.clear()
    closed = client.get(f"{VERIFY}/{code}")
    assert closed.status_code == 404
    assert closed.json() == {"detail": "Not found"}

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    open_the_site(client)
    client.cookies.clear()
    assert client.get(f"{VERIFY}/{code}").status_code == 200


def test_both_verify_namespaces_resolve_independently(
    client, db_session, admin_account, admin_headers
):
    """/certificates/verify deliberately avoids 017's /verify: the email
    verification POST keeps answering as 017 built it, and the certificate
    GET answers as 019 built it, each at its own path."""
    _, enrollment, _ = make_completed(db_session)
    open_the_site(client)
    client.cookies.clear()

    email_verify = client.post("/api/v1/verify", json={"token": "nope"})
    assert email_verify.status_code == 422
    assert email_verify.json()["errors"] == [registration_service.VERIFY_FAILED]

    certificate = client.get(
        f"{VERIFY}/{enrollment.completion.verification_token}"
    )
    assert certificate.status_code == 200
    assert certificate.json()["valid"] is True


def test_rate_limit_config_present():
    """The Caddy zone for the public verification GET, mirroring the
    signup rule — asserted here so removing the config line fails a test
    by name."""
    caddyfile = (
        Path(__file__).resolve().parents[2] / "deploy" / "Caddyfile"
    ).read_text()
    assert "zone certificate_verification" in caddyfile
    assert "/api/v1/certificates/verify/*" in caddyfile
