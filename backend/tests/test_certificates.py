"""Feature 010: certificate rendering from the snapshot alone (9.01), the
issuance split, the 60-day finding, and the deletion/unpublish guarantees.
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO

from pypdf import PdfReader

from app.services import certificates, completions, enrollments, readiness
from app.services import courses as courses_service
from app.services import sponsor as sponsor_service
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, make_account
from tests.test_completion import complete_profile, make_completed
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    answer_all_reviews,
    enroll,
    make_participant,
    make_published_course,
)


def pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


# --- rendering from the snapshot --------------------------------------------


def test_certificate_text_carries_every_item(db_session):
    _, enrollment, _ = make_completed(db_session)
    snapshot = enrollment.completion.certificate_snapshot
    text = pdf_text(certificates.render(snapshot))

    assert "superCPE" in text  # item 1
    assert "RYZE.AI LLC" in text  # 9.01.1
    assert "Pat Smith" in text  # item 2
    assert "Course GOLD" in text and "GOLD" in text  # item 3
    assert snapshot["completed_at"][:10] in text  # item 4
    assert "Not applicable (self study)" in text  # item 5
    assert "Self study" in text  # item 6
    assert "0.4 in Accounting" in text  # item 7
    assert "National Registry" not in text  # item 8 absent
    assert (
        "CPE credits have been granted based on a 50-minute hour." in text
    )  # item 10
    assert "Retain this certificate." in text  # item 11
    assert "Dev CPA" in text and "Rev CPA" in text
    assert snapshot["certificate_number"] in text
    assert snapshot["verification_token"] in text
    assert "Certificate of Completion" in text


def test_unicode_names_render_and_extract_unchanged(db_session):
    """011's font fix: the vendored DejaVu faces render names beyond
    Latin-1 (010 sanitized them to replacement characters). The two
    characters the spec names: "ễ" and "ł"."""
    _, enrollment, _ = make_completed(db_session)
    snapshot = dict(enrollment.completion.certificate_snapshot)
    snapshot["participant_name"] = "Nguyễn Michałowski"
    pdf = certificates.render(snapshot)
    assert "Nguyễn Michałowski" in pdf_text(pdf)

    # The embedded fonts are the vendored ones, not a core Latin-1 face.
    reader = PdfReader(BytesIO(pdf))
    fonts = {
        str(font.get_object()["/BaseFont"])
        for page in reader.pages
        for font in page["/Resources"]["/Font"].values()
    }
    assert all("DejaVuSans" in name for name in fonts)


def test_rerender_produces_the_same_text(db_session):
    _, enrollment, _ = make_completed(db_session)
    snapshot = enrollment.completion.certificate_snapshot
    assert pdf_text(certificates.render(snapshot)) == pdf_text(
        certificates.render(snapshot)
    )


def test_item_8_prints_when_the_snapshot_carries_it(db_session):
    complete_profile(db_session)
    profile = sponsor_service.get_profile(db_session)
    profile.registry_status = "registered"
    profile.national_registry_id = "112233"
    db_session.commit()
    _, enrollment, _ = make_completed_without_profile(db_session)
    text = pdf_text(
        certificates.render(enrollment.completion.certificate_snapshot)
    )
    assert "National Registry of CPE Sponsors ID: 112233" in text


def make_completed_without_profile(db_session):
    """make_completed minus the profile reset, for tests that configured
    the profile themselves."""
    from tests.test_completion import sit

    course, _ = make_published_course(db_session)
    participant = make_participant(db_session)
    enrollment = enroll(db_session, course, participant)
    answer_all_reviews(db_session, enrollment)
    attempt = sit(db_session, enrollment)
    assert attempt.status == "passed"
    return course, enrollment, attempt


def test_state_registrations_print(db_session):
    complete_profile(db_session)
    sponsor_service.set_state_registrations(
        db_session,
        [{"state": "NH", "registration_number": "NH-42", "notes": ""}],
    )
    _, enrollment, _ = make_completed_without_profile(db_session)
    text = pdf_text(
        certificates.render(enrollment.completion.certificate_snapshot)
    )
    assert "NH sponsor registration number: NH-42" in text


# --- issuance ---------------------------------------------------------------


def blank_legal_name_profile(db):
    return sponsor_service.update_profile(
        db,
        {
            "name": "superCPE",
            "legal_name": "",
            "registry_status": "not_registered",
            "national_registry_id": "",
            "website": "",
            "contact_email": "",
            "contact_phone": "",
            "address": "",
            "other_certificate_statements": "",
        },
    )


def test_issuance_waits_on_sponsor_fields_but_completion_does_not(
    client, admin_headers, db_session
):
    blank_legal_name_profile(db_session)
    _, enrollment, _ = make_completed_without_profile(db_session)
    completion = enrollment.completion

    # The 9.02.2(1) record does not wait on the sponsor's paperwork...
    assert completion.certificate_key is None
    assert completions.certificate_ready(db_session, completion) is False
    assert completions.missing_for_issuance(db_session) == ["legal_name"]

    # ...the participant is told the certificate is pending...
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    [card] = client.get("/api/v1/my/courses").json()
    assert card["completion"]["certificate_ready"] is False
    download = client.get(
        f"/api/v1/my/completions/{completion.id}/certificate.pdf"
    )
    assert download.status_code == 409
    assert "will be issued shortly" in download.json()["errors"][0]

    # ...and the admin render refuses, naming the missing field.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    refused = client.post(f"/api/v1/admin/completions/{completion.id}/render")
    assert refused.status_code == 422
    assert "legal_name" in refused.json()["errors"][0]

    # Filling the field unblocks the render — and, deliberately, the legal
    # name filled after completion is NOT on the certificate: the snapshot
    # is the truth and it was taken when the credit was earned.
    profile = sponsor_service.get_profile(db_session)
    profile.legal_name = "Late Paperwork LLC"
    db_session.commit()
    rendered = client.post(f"/api/v1/admin/completions/{completion.id}/render")
    assert rendered.status_code == 200, rendered.json()
    assert rendered.json()["certificate_rendered_at"] is not None

    pdf = client.get(f"/api/v1/admin/completions/{completion.id}/certificate.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    text = pdf_text(pdf.content)
    assert "Late Paperwork LLC" not in text
    assert "superCPE" in text


def test_participant_download_renders_when_fields_allow(client, db_session):
    _, enrollment, _ = make_completed(db_session)
    completion = enrollment.completion
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    response = client.get(
        f"/api/v1/my/completions/{completion.id}/certificate.pdf"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Pat Smith" in pdf_text(response.content)
    db_session.refresh(completion)
    assert completion.certificate_key == (
        f"certificates/{completion.certificate_number}.pdf"
    )

    # A foreign completion is 404.
    make_account(
        db_session, "other@supercpe.test", PARTICIPANT_PASSWORD, "participant"
    )
    login(client, "other@supercpe.test", PARTICIPANT_PASSWORD)
    assert (
        client.get(
            f"/api/v1/my/completions/{completion.id}/certificate.pdf"
        ).status_code
        == 404
    )


# --- the 60-day finding -----------------------------------------------------


def test_certificates_overdue_after_60_days(db_session):
    blank_legal_name_profile(db_session)
    _, enrollment, _ = make_completed_without_profile(db_session)
    completion = enrollment.completion

    completion.completed_at = datetime.now(timezone.utc) - timedelta(days=59)
    db_session.commit()
    assert readiness.sponsor_findings(db_session) == []

    completion.completed_at = datetime.now(timezone.utc) - timedelta(days=61)
    db_session.commit()
    [finding] = readiness.sponsor_findings(db_session)
    assert finding.code == "certificates_overdue"
    assert finding.level == "warn"
    assert completion.certificate_number in finding.message


def test_admin_sponsor_payload_carries_the_finding(
    client, admin_headers, db_session
):
    blank_legal_name_profile(db_session)
    _, enrollment, _ = make_completed_without_profile(db_session)
    enrollment.completion.completed_at = datetime.now(timezone.utc) - timedelta(
        days=61
    )
    db_session.commit()
    body = client.get("/api/v1/admin/sponsor", headers=admin_headers).json()
    assert body["missing_for_issuance"] == ["legal_name"]
    [finding] = body["findings"]
    assert finding["code"] == "certificates_overdue"


# --- deletion and unpublish -------------------------------------------------


def test_delete_course_with_enrollments_refused(client, admin_headers, db_session):
    course, enrollment, _ = make_completed(db_session)
    courses_service.unpublish(db_session, course)
    response = client.delete(
        f"/api/v1/admin/courses/{course.course_code}", headers=admin_headers
    )
    assert response.status_code == 422
    assert any("1 enrollment" in e for e in response.json()["errors"])


def test_unpublish_leaves_an_active_enrollment_working(client, db_session):
    complete_profile(db_session)
    course, _ = make_published_course(db_session)
    participant = make_participant(db_session)
    enrollment = enroll(db_session, course, participant)
    courses_service.unpublish(db_session, course)

    assert enrollments.status(enrollment) == "active"
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    [package_id] = [int(pid) for pid in enrollment.package_versions]
    play = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/lessons/{package_id}/play"
    )
    assert play.status_code == 200
    assert play.json()["lesson_id"] == "GOLD-01"
