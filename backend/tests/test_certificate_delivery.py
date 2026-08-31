"""Feature 019: certificate delivery by email — a courtesy layered on the
record.

The load-bearing tests: completion sends exactly one `certificate` email
with the PDF attached, a refused send still completes and is recorded as
`failed`, the admin Resend recovers it, and a render blocked by sponsor
fields leaves delivery `pending` with no failure anywhere. Nothing in the
completion path gained a new failure mode.
"""

from sqlalchemy import select

from app.models.email_message import EmailMessage
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_certificates import blank_legal_name_profile
from tests.test_completion import complete_profile
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    answer_all_reviews,
    setup_enrolled,
)


def pass_the_assessment(client, db_session, enrollment):
    """The participant path end to end: the submit route owns the
    completion transaction, and 019's delivery hangs off it."""
    answer_all_reviews(db_session, enrollment)
    start = client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment/attempts"
    )
    assert start.status_code == 201, start.json()
    attempt_id = start.json()["attempt_id"]
    info = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment"
    ).json()
    answers = {
        str(q["question_id"]): q["choices"][0]["choice_id"]
        for q in info["questions"]
    }
    return client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment/attempts"
        f"/{attempt_id}/submit",
        json={"answers": answers},
    )


def certificate_emails(db_session):
    return list(
        db_session.scalars(
            select(EmailMessage)
            .where(EmailMessage.kind == "certificate")
            .order_by(EmailMessage.id)
        )
    )


def test_completion_sends_exactly_one_certificate_email(
    client, db_session, console_email
):
    complete_profile(db_session)
    _, _, enrollment = setup_enrolled(client, db_session)
    response = pass_the_assessment(client, db_session, enrollment)
    assert response.status_code == 200
    assert response.json()["status"] == "passed"

    completion = enrollment.completion
    [message] = certificate_emails(db_session)
    assert message.recipient == PARTICIPANT_EMAIL
    assert message.backend == "console"
    assert message.attachment_filename == (
        f"certificate-{completion.certificate_number}.pdf"
    )

    db_session.refresh(completion)
    assert completion.delivery_status == "sent"
    assert completion.delivered_at is not None
    # The render happened on the way (the attachment had to come from
    # somewhere), so the participant's download needs no second render.
    assert completion.certificate_key is not None

    # The participant surface carries the code and the delivery is
    # invisible there — their download works either way.
    [card] = client.get("/api/v1/my/courses").json()
    assert card["completion"]["verification_code"] == (
        completion.verification_token
    )


def test_send_failure_leaves_completion_intact_and_resend_recovers(
    client, db_session, console_email, monkeypatch, admin_account
):
    complete_profile(db_session)
    course, _, enrollment = setup_enrolled(client, db_session)

    def refuse(*args, **kwargs):
        raise RuntimeError("the backend is down")

    with monkeypatch.context() as patched:
        patched.setattr("app.services.email.send", refuse)
        response = pass_the_assessment(client, db_session, enrollment)

    # The completion is untouched by the failed send.
    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    completion = enrollment.completion
    assert completion is not None
    db_session.refresh(completion)
    assert completion.delivery_status == "failed"
    assert completion.delivered_at is None
    assert certificate_emails(db_session) == []

    # The failure is surfaced on the admin completions view...
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    [row] = client.get(
        f"/api/v1/admin/courses/{course.course_code}/completions"
    ).json()
    assert row["delivery_status"] == "failed"
    assert row["delivered_at"] is None

    # ...and the Resend button recovers it.
    resent = client.post(f"/api/v1/admin/completions/{completion.id}/resend")
    assert resent.status_code == 200, resent.json()
    assert resent.json()["delivery_status"] == "sent"
    assert resent.json()["delivered_at"] is not None
    [message] = certificate_emails(db_session)
    assert message.recipient == PARTICIPANT_EMAIL
    db_session.refresh(completion)
    assert completion.delivery_status == "sent"


def test_blocked_issuance_leaves_delivery_pending_not_failed(
    client, db_session, console_email, admin_account
):
    """While the sponsor's fields block the render there is nothing to
    send: no email, no failure, delivery pending — and the completion
    stands, exactly as 010 promised."""
    blank_legal_name_profile(db_session)
    _, _, enrollment = setup_enrolled(client, db_session)
    response = pass_the_assessment(client, db_session, enrollment)
    assert response.json()["status"] == "passed"

    completion = enrollment.completion
    db_session.refresh(completion)
    assert completion.delivery_status == "pending"
    assert certificate_emails(db_session) == []

    # Resend while blocked refuses, naming the field, like the render.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    refused = client.post(f"/api/v1/admin/completions/{completion.id}/resend")
    assert refused.status_code == 422
    assert "legal_name" in refused.json()["errors"][0]

    # Filling the field unblocks it: Resend renders and sends in one act.
    from app.services import sponsor as sponsor_service

    profile = sponsor_service.get_profile(db_session)
    profile.legal_name = "Late Paperwork LLC"
    db_session.commit()
    resent = client.post(f"/api/v1/admin/completions/{completion.id}/resend")
    assert resent.status_code == 200, resent.json()
    assert resent.json()["delivery_status"] == "sent"
    [message] = certificate_emails(db_session)
    assert message.attachment_filename == (
        f"certificate-{completion.certificate_number}.pdf"
    )
