"""Feature 021: waiting-list invitations — the one promised email.

The load-bearing tests: the send refuses while coming_soon with nothing
emailed; one run at open sends exactly one `invitation` email per active
entry and the summary adds up; a re-run attempts zero (the button is the
retry); a forced per-row failure marks `failed` without stopping the run
and both the re-run and the per-row Resend recover it; removed entries —
before the run or after a failure — are never emailed; and the rendered
message carries the two links, the never-again line, and no course fact
beyond the naming sentence ("National Registry" pinned absent).
"""

from sqlalchemy import select

from app.models.email_message import EmailMessage
from app.models.waiting_list import WaitingListEntry
from app.services import invitations
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_enrollments import make_published_course
from tests.test_site import open_the_site

SIGNUP_URL = "/api/v1/waiting-list"
ADMIN_URL = "/api/v1/admin/waiting-list"
SEND_URL = f"{ADMIN_URL}/invitations"
EXPORT_URL = f"{ADMIN_URL}/export.csv"

PAT = {"name": "Pat Example", "email": "pat@example.test", "state": "NH"}
RILEY = {"name": "Riley Reader", "email": "riley@example.test", "state": "VT"}


def sign_up(client, **person):
    response = client.post(SIGNUP_URL, json={"firm": "", **person})
    assert response.status_code == 200, response.json()


def entry_by_email(db_session, email):
    entry = db_session.scalar(
        select(WaitingListEntry).where(WaitingListEntry.email == email)
    )
    db_session.refresh(entry)
    return entry


def invitation_emails(db_session):
    return list(
        db_session.scalars(
            select(EmailMessage)
            .where(EmailMessage.kind == "invitation")
            .order_by(EmailMessage.id)
        )
    )


def open_with_course(client, db_session):
    """Signups happen while coming_soon (the form 404s at open), so call
    this after them: admin session, published course, flipped open."""
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    course, _ = make_published_course(db_session)
    open_the_site(client)
    return course


def fail_sends_to(monkeypatch, *recipients):
    """Patch 017's send to refuse for the given recipients only."""
    from app.services import email as email_service

    real_send = email_service.send

    def selective(db, kind, recipient, subject, body, attachment=None):
        if recipient in recipients:
            raise RuntimeError("the backend is down")
        return real_send(db, kind, recipient, subject, body, attachment)

    monkeypatch.setattr("app.services.email.send", selective)


# --- The refusal -------------------------------------------------------------


def test_refuses_while_coming_soon_and_nothing_is_emailed(
    client, db_session, console_email, admin_account
):
    sign_up(client, **PAT)
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    response = client.post(SEND_URL)
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "coming_soon" in error
    assert "404" in error  # the message says why, not just no

    assert invitation_emails(db_session) == []
    pat = entry_by_email(db_session, PAT["email"])
    assert pat.invitation_status is None
    assert pat.invited_at is None

    # The per-row Resend refuses the same way.
    resent = client.post(f"{ADMIN_URL}/{pat.id}/resend")
    assert resent.status_code == 422
    assert "coming_soon" in resent.json()["errors"][0]


# --- The run -----------------------------------------------------------------


def test_full_run_sends_one_invitation_per_active_entry(
    client, db_session, console_email, admin_account
):
    sign_up(client, **PAT)
    sign_up(client, **RILEY)
    sign_up(client, name="Gone Gonzales", email="gone@example.test", state="ME")
    open_with_course(client, db_session)
    gone = entry_by_email(db_session, "gone@example.test")
    client.post(f"{ADMIN_URL}/{gone.id}/remove", json={"reason": "asked"})

    response = client.post(SEND_URL)
    assert response.status_code == 200, response.json()
    assert response.json() == {
        "attempted": 2,
        "sent": 2,
        "failed": 0,
        "skipped_already_invited": 0,
    }

    # One outbound `invitation` email per active entry, none for the
    # removed one, and the log matches the row statuses.
    messages = invitation_emails(db_session)
    assert sorted(m.recipient for m in messages) == [
        PAT["email"], RILEY["email"],
    ]
    for email in (PAT["email"], RILEY["email"]):
        entry = entry_by_email(db_session, email)
        assert entry.invitation_status == "sent"
        assert entry.invited_at is not None
    gone = entry_by_email(db_session, "gone@example.test")
    assert gone.invitation_status is None
    assert gone.invited_at is None

    # The admin listing carries the 021 counts and per-row status...
    listing = client.get(ADMIN_URL).json()
    assert (listing["invited"], listing["failed"], listing["invitable"]) == (
        2, 0, 0,
    )
    assert all(e["invitation_status"] == "sent" for e in listing["entries"])

    # ...and the CSV carries the two new columns, filled.
    header, *rows = (
        client.get(EXPORT_URL).content.decode("utf-8").strip().splitlines()
    )
    assert header.endswith(",invited_at,invitation_status")
    assert len(rows) == 2
    assert all(row.endswith(",sent") for row in rows)


def test_rerun_attempts_zero(client, db_session, console_email, admin_account):
    sign_up(client, **PAT)
    open_with_course(client, db_session)
    assert client.post(SEND_URL).json()["sent"] == 1

    rerun = client.post(SEND_URL).json()
    assert rerun == {
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "skipped_already_invited": 1,
    }
    [message] = invitation_emails(db_session)
    assert message.recipient == PAT["email"]


# --- Failure and recovery ----------------------------------------------------


def test_failure_marks_failed_without_stopping_and_the_rerun_recovers(
    client, db_session, console_email, admin_account, monkeypatch
):
    sign_up(client, **PAT)
    sign_up(client, **RILEY)
    open_with_course(client, db_session)

    with monkeypatch.context() as patched:
        fail_sends_to(patched, PAT["email"])
        response = client.post(SEND_URL)
    assert response.json() == {
        "attempted": 2,
        "sent": 1,
        "failed": 1,
        "skipped_already_invited": 0,
    }
    pat = entry_by_email(db_session, PAT["email"])
    assert pat.invitation_status == "failed"
    assert pat.invited_at is not None  # the failed attempt is on record
    assert entry_by_email(db_session, RILEY["email"]).invitation_status == "sent"
    [message] = invitation_emails(db_session)
    assert message.recipient == RILEY["email"]

    # The batch button is the retry: the re-run reaches only the failed row.
    rerun = client.post(SEND_URL).json()
    assert rerun == {
        "attempted": 1,
        "sent": 1,
        "failed": 0,
        "skipped_already_invited": 1,
    }
    pat = entry_by_email(db_session, PAT["email"])
    assert pat.invitation_status == "sent"
    assert sorted(m.recipient for m in invitation_emails(db_session)) == [
        PAT["email"], RILEY["email"],
    ]


def test_per_row_resend_recovers_a_failed_row(
    client, db_session, console_email, admin_account, monkeypatch
):
    sign_up(client, **PAT)
    sign_up(client, **RILEY)
    open_with_course(client, db_session)
    with monkeypatch.context() as patched:
        fail_sends_to(patched, PAT["email"])
        client.post(SEND_URL)
    pat = entry_by_email(db_session, PAT["email"])

    response = client.post(f"{ADMIN_URL}/{pat.id}/resend")
    assert response.status_code == 200, response.json()
    db_session.refresh(pat)
    assert pat.invitation_status == "sent"
    row = next(
        e for e in response.json()["entries"] if e["email"] == PAT["email"]
    )
    assert row["invitation_status"] == "sent"

    # Never a second successful invitation: Resend on a sent row refuses.
    again = client.post(f"{ADMIN_URL}/{pat.id}/resend")
    assert again.status_code == 422
    assert "already invited" in again.json()["errors"][0]
    assert client.post(f"{ADMIN_URL}/999/resend").status_code == 404


def test_removed_after_a_failure_is_never_emailed(
    client, db_session, console_email, admin_account, monkeypatch
):
    sign_up(client, **PAT)
    open_with_course(client, db_session)
    with monkeypatch.context() as patched:
        fail_sends_to(patched, PAT["email"])
        client.post(SEND_URL)
    pat = entry_by_email(db_session, PAT["email"])
    client.post(f"{ADMIN_URL}/{pat.id}/remove", json={"reason": "asked"})

    # Neither the re-run nor the per-row Resend reaches a removed row.
    assert client.post(SEND_URL).json() == {
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "skipped_already_invited": 0,
    }
    resent = client.post(f"{ADMIN_URL}/{pat.id}/resend")
    assert resent.status_code == 422
    assert "removed" in resent.json()["errors"][0]
    assert invitation_emails(db_session) == []


# --- The message itself ------------------------------------------------------


def test_rendered_invitation_is_links_not_disclosure(
    client, db_session, admin_account
):
    """8.01 restraint, pinned: the two links and the naming sentence are
    the whole substance — the course page carries the disclosure, the
    email carries a link to it — plus the never-again line keeping 015's
    promise. "National Registry" never appears, conditional or not."""
    course = open_with_course(client, db_session)
    subject, body = invitations.render_invitation(
        "Pat Example", course, "superCPE"
    )

    assert "superCPE" in subject
    assert f"/courses/{course.course_code}" in body
    assert "/register" in body
    assert course.title in body
    assert "will not email you again" in body

    for absent in (
        "National Registry",
        "national_registry",
        "Accounting",  # the course's field of study
        "CPE credit",
        "$",  # no price
    ):
        assert absent not in subject + body, absent
