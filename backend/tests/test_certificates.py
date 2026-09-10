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
    # 019: the printed verification line — the code, and the public page's
    # path (which deliberately avoids 017's /verify).
    assert snapshot["verification_token"] in text
    assert "supercpe.com/certificates/verify" in text
    assert "Verify this certificate" in text
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


# --- 023c D1: placement, not presence --------------------------------------


_PAGE_WIDTH_PT = 612
_PAGE_HEIGHT_PT = 792
_MARGIN_PT = 20 * 72 / 25.4  # the renderer's 20 mm margin


def positioned_runs(pdf_bytes: bytes) -> list[dict]:
    """Every text run on page one with its start x/y (from the text
    matrix) and its end x, measured with the same font metrics the
    renderer used. Text extraction alone ignores the page boundary — this
    is what let 2026-000001 ship with most 9.01 items past x=612."""
    from fpdf import FPDF

    from app.services.certificates import _FONTS_DIR

    ruler = FPDF()
    ruler.add_font("DejaVu", "", _FONTS_DIR / "DejaVuSans.ttf")
    ruler.add_font("DejaVu", "B", _FONTS_DIR / "DejaVuSans-Bold.ttf")
    ruler.add_font("DejaVu", "I", _FONTS_DIR / "DejaVuSans-Oblique.ttf")

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert [float(v) for v in page.mediabox] == [0, 0, _PAGE_WIDTH_PT, _PAGE_HEIGHT_PT]
    runs = []

    def visit(text, cm, tm, font_dict, font_size):
        if not text.strip():
            return
        base_font = str(font_dict["/BaseFont"])
        style = "B" if "Bold" in base_font else "I" if "Oblique" in base_font else ""
        ruler.set_font("DejaVu", style, font_size)
        width_pt = ruler.get_string_width(text) * 72 / 25.4
        runs.append(
            {
                "text": text,
                "x": float(tm[4]),
                "y": float(tm[5]),
                "end_x": float(tm[4]) + width_pt,
            }
        )

    page.extract_text(visitor_text=visit)
    return runs


def test_every_text_run_lies_inside_the_page(db_session):
    """Realistic snapshot: a course title that wraps, a legal entity name,
    a sponsor ID, a state registration, and a verification code. Every run
    starts and ends inside the margins, and every applicable 9.01 item is
    among the in-page runs."""
    _, enrollment, _ = make_completed(db_session)
    snapshot = dict(enrollment.completion.certificate_snapshot)
    snapshot["course_title"] = (
        "Account Takeover: How Attackers Get In, How to Stop It, and Why "
        "Every Firm With a Cloud Login Should Care"
    )
    snapshot["national_registry_id"] = "112233"
    snapshot["state_registrations"] = [{"state": "NH", "number": "NH-42"}]
    snapshot["other_statements"] = ["Retain this certificate."]

    runs = positioned_runs(certificates.render(snapshot))
    assert len(runs) >= 18
    for run in runs:
        assert _MARGIN_PT - 1 <= run["x"] <= _PAGE_WIDTH_PT - _MARGIN_PT, run
        assert run["end_x"] <= _PAGE_WIDTH_PT - _MARGIN_PT + 1, run
        assert _MARGIN_PT <= run["y"] <= _PAGE_HEIGHT_PT - _MARGIN_PT, run

    in_page = "\n".join(run["text"] for run in runs)
    assert "superCPE" in in_page  # item 1
    assert "RYZE.AI LLC" in in_page  # 9.01.1
    assert "Pat Smith" in in_page  # item 2
    assert "Account Takeover: How Attackers Get In, How to Stop It," in in_page
    assert "Every Firm With a Cloud Login Should Care" in in_page  # item 3, wrapped
    assert f"Completion date: {snapshot['completed_at'][:10]}" in in_page  # 4
    assert "Location: Not applicable (self study)" in in_page  # item 5
    assert "Type of learning program: Self study" in in_page  # item 6
    assert "CPE credit: 0.4 in Accounting" in in_page  # item 7
    assert "National Registry of CPE Sponsors ID: 112233" in in_page  # 8
    assert "NH sponsor registration number: NH-42" in in_page  # item 9
    assert "CPE credits have been granted based on a 50-minute hour." in in_page
    assert "Retain this certificate." in in_page  # item 11
    assert "Developed by Dev CPA" in in_page and "Reviewed by Rev CPA" in in_page
    assert f"Certificate number: {snapshot['certificate_number']}" in in_page
    assert snapshot["verification_token"] in in_page  # 019

    # Each line begins near the centre of the page, not at the previous
    # line's right edge: the widest run is the wrapped title, and even it
    # starts well right of the margin.
    assert all(run["x"] > _MARGIN_PT for run in runs)
