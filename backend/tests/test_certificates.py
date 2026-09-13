"""Feature 010: certificate rendering from the snapshot alone (9.01), the
issuance split, the 60-day finding, and the deletion/unpublish guarantees.
032: the same assertions against the HTML-template renderer, plus the
mark (uploaded logo or the brand logo), the palette sync, the toolchain, and the admin
preview.
"""

import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from weasyprint import HTML

from app.assets.brand.palette import PALETTE
from app.models.enrollment import Completion
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
    """Every text run on page one with its start x/y and its end x, in
    PDF points, measured with the same font files the renderer embeds.
    Text extraction alone ignores the page boundary — this is what let
    2026-000001 ship with most 9.01 items past x=612.

    032: WeasyPrint draws in CSS px under a page transform (the `cm`
    that scales to pt and flips y), so the visitor's `cm` and `tm` are
    composed here. Widths are the faces' advance widths (fontTools);
    the stylesheet turns kerning off, so the sum is the drawn width.
    Letter-spacing on the heading adds width this does not count, which
    only makes the boundary check stricter on the left and looser on
    the right by a few dozen points for that one centred line."""
    from fontTools.ttLib import TTFont

    from app.services.certificates import _FONTS_DIR

    faces = {
        "": TTFont(_FONTS_DIR / "DejaVuSans.ttf"),
        "B": TTFont(_FONTS_DIR / "DejaVuSans-Bold.ttf"),
        "I": TTFont(_FONTS_DIR / "DejaVuSans-Oblique.ttf"),
    }

    def width_pt(text: str, style: str, size_pt: float) -> float:
        face = faces[style]
        cmap = face.getBestCmap()
        widths = face["hmtx"]
        units = sum(
            widths[cmap.get(ord(character), ".notdef")][0] for character in text
        )
        return units * size_pt / face["head"].unitsPerEm

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert [float(v) for v in page.mediabox] == [0, 0, _PAGE_WIDTH_PT, _PAGE_HEIGHT_PT]
    runs = []

    def visit(text, cm, tm, font_dict, font_size):
        text = text.rstrip("\n")
        if not text.strip():
            return
        base_font = str(font_dict["/BaseFont"])
        style = "B" if "Bold" in base_font else "I" if "Italic" in base_font else ""
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        size_pt = font_size * abs(cm[0]) * abs(tm[0])
        runs.append(
            {
                "text": text,
                "x": float(x),
                "y": float(y),
                "end_x": float(x) + width_pt(text, style, size_pt),
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


# --- 032: the template renderer -------------------------------------------


REPO = Path(__file__).resolve().parents[2]
GLOBAL_CSS = REPO / "frontend" / "src" / "styles" / "global.css"
BRAND_DIR = REPO / "backend" / "app" / "assets" / "brand"


def raster_images(pdf_bytes: bytes) -> list[tuple[int, int]]:
    """(width, height) of every raster image object on page one, Form
    XObjects included. An SVG mark is drawn as paths and leaves none."""
    reader = PdfReader(BytesIO(pdf_bytes))
    found = []

    def walk(resources):
        for xobject in (resources.get("/XObject") or {}).values():
            xobject = xobject.get_object()
            if xobject.get("/Subtype") == "/Image":
                found.append((int(xobject["/Width"]), int(xobject["/Height"])))
            elif xobject.get("/Subtype") == "/Form":
                walk(xobject.get("/Resources") or {})

    walk(reader.pages[0]["/Resources"])
    return found


def png_logo(width: int = 40, height: int = 20) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (width, height), PALETTE["accent"]).save(buffer, "PNG")
    return buffer.getvalue()


def bare_snapshot(**overrides) -> dict:
    """A snapshot written by hand — no session, no profile row, no
    course — with every key `create` writes. Pins the contract that
    `render` needs nothing but the dict."""
    snapshot = {
        "sponsor_name": "superCPE",
        "sponsor_legal_name": "RYZE.AI LLC",
        "participant_name": "Pat Smith",
        "participant_email": "pat@supercpe.test",
        "course_title": "Course GOLD",
        "course_code": "GOLD",
        "completed_at": "2026-09-13T15:30:00+00:00",
        "location": None,
        "program_type": "Self study",
        "credit": "0.4",
        "field_of_study": "Accounting",
        "national_registry_id": None,
        "state_registrations": [],
        "time_statement": "CPE credits have been granted based on a 50-minute hour.",
        "other_statements": [],
        "knowledge_level": "Basic",
        "package_versions": {},
        "passing_pct": "70",
        "score_pct": "100",
        "recommended_credit_basis": "Word count formula, 2026 Standards 7.02.6",
        "developed_by": None,
        "reviewed_by": None,
        "certificate_number": "2026-000001",
        "verification_token": "a" * 64,
    }
    snapshot.update(overrides)
    return snapshot


def test_toolchain_renders_minimal_html_to_one_page():
    """The renderer is installed with its system stack: a trivial page
    lays out (this is what preflight and boot check)."""
    pdf = HTML(string="<html><body><p>ok</p></body></html>").write_pdf()
    assert pdf.startswith(b"%PDF")
    assert len(PdfReader(BytesIO(pdf)).pages) == 1
    certificates.ensure_renderer_available()
    assert certificates.renderer_check() == "ok"


def test_render_needs_only_the_snapshot():
    """No session, no profile row, no course: the dict is the whole
    input, and the result is one page carrying the items."""
    pdf = certificates.render(bare_snapshot())
    assert len(PdfReader(BytesIO(pdf)).pages) == 1
    text = pdf_text(pdf)
    assert "Pat Smith" in text
    assert "Authorized by RYZE.AI LLC" in text
    assert "Certificate number: 2026-000001" in text


def test_item_8_absent_prints_neither_the_id_nor_the_words():
    text = pdf_text(certificates.render(bare_snapshot(national_registry_id=None)))
    assert "National Registry" not in text
    assert "Sponsors ID" not in text


def test_item_8_present_prints_from_the_snapshot_alone():
    text = pdf_text(certificates.render(bare_snapshot(national_registry_id="112233")))
    assert "National Registry of CPE Sponsors ID: 112233" in text


def test_item_9_prints_only_the_registrations_held():
    text = pdf_text(certificates.render(bare_snapshot(state_registrations=[])))
    assert "sponsor registration number" not in text
    text = pdf_text(
        certificates.render(
            bare_snapshot(
                state_registrations=[
                    {"state": "NH", "number": "NH-42"},
                    {"state": "TX", "number": "TX-7"},
                ]
            )
        )
    )
    assert "NH sponsor registration number: NH-42" in text
    assert "TX sponsor registration number: TX-7" in text


def test_long_content_stays_on_one_page():
    """The frame clips: a snapshot with many statements still yields
    exactly one page (the 9.02 record is a one-page PDF)."""
    pdf = certificates.render(
        bare_snapshot(
            other_statements=[f"Board statement number {n}." for n in range(40)],
            state_registrations=[
                {"state": f"S{n}", "number": f"R-{n}"} for n in range(20)
            ],
        )
    )
    assert len(PdfReader(BytesIO(pdf)).pages) == 1


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def test_brand_logo_is_the_mark_without_an_upload():
    """033: no upload → the committed brand logo, referenced by a file:
    URL under app/assets/brand/ (the fetcher admits it), and the brand
    mark as the seal. Both are embedded at their pixel size."""
    html = certificates.render_html(bare_snapshot())
    assert certificates.BRAND_LOGO_PATH.as_uri() in html
    assert certificates.BRAND_MARK_PATH.as_uri() in html
    assert certificates.BRAND_LOGO_PATH.is_relative_to(certificates._ASSETS_DIR)
    assert "data:" not in html
    pdf = certificates.render(bare_snapshot())
    assert sorted(raster_images(pdf)) == sorted(
        [image_size(certificates.BRAND_LOGO_PATH), image_size(certificates.BRAND_MARK_PATH)]
    )


def test_uploaded_logo_is_embedded():
    logo = certificates.Logo(png_logo(40, 20), "image/png")
    pdf = certificates.render(bare_snapshot(), logo=logo)
    # The upload replaces the brand logo at the top; the seal stays.
    assert sorted(raster_images(pdf)) == sorted(
        [(40, 20), image_size(certificates.BRAND_MARK_PATH)]
    )
    # And the text is untouched by the mark.
    assert "Pat Smith" in pdf_text(pdf)


def test_two_renders_of_one_snapshot_are_byte_identical():
    """033: the creation date is the snapshot's completion instant, not
    the clock, so the stored-once record (9.02) is checkable by
    comparison."""
    snapshot = bare_snapshot()
    first, second = certificates.render(snapshot), certificates.render(snapshot)
    assert first == second
    metadata = PdfReader(BytesIO(first)).metadata
    assert metadata["/CreationDate"].startswith("D:20260913")
    assert len(first) < 500 * 1024


def test_certificate_is_self_contained():
    """Fonts and images are embedded and nothing points outside the
    file: the PDF opens with the network off. Every embedded font is a
    vendored DejaVu face; no annotation, URI action, or external stream
    reference exists."""
    pdf = certificates.render(bare_snapshot(national_registry_id="112233"))
    reader = PdfReader(BytesIO(pdf))
    [page] = reader.pages
    fonts = page["/Resources"]["/Font"]
    assert fonts, "no fonts embedded"
    for font in fonts.values():
        font = font.get_object()
        descriptor = font.get("/FontDescriptor") or font["/DescendantFonts"][0].get_object()["/FontDescriptor"]
        descriptor = descriptor.get_object()
        assert any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")), font
        assert "DejaVuSans" in str(font["/BaseFont"])
    assert "/Annots" not in page
    assert b"/URI" not in pdf and b"http://" not in pdf and b"https://" not in pdf
    assert b"/F (" not in pdf  # no external file specification
    assert len(raster_images(pdf)) == 2  # the logo and the seal, both inline


def test_no_registry_words_without_the_claim():
    """003's rule on the brand assets: the template, the CSS, the brand
    images' names, and the rendered text carry no Registry words while
    the snapshot does not claim item 8."""
    text = pdf_text(certificates.render(bare_snapshot(national_registry_id=None)))
    assert "National Registry" not in text
    for path in (
        certificates._TEMPLATES_DIR / "certificate.css",
        certificates.BRAND_LOGO_PATH,
        certificates.BRAND_MARK_PATH,
    ):
        assert "registry" not in path.name.lower()
    css = (certificates._TEMPLATES_DIR / "certificate.css").read_text()
    assert "Registry" not in css


def test_renderer_fetches_nothing_but_assets():
    fetcher = certificates._AssetsOnlyFetcher()
    fonts_dir = certificates._FONTS_DIR
    response = fetcher.fetch((fonts_dir / "DejaVuSans.ttf").as_uri())
    assert response.read(4) == b"\x00\x01\x00\x00"  # a TrueType file
    response.close()
    for url in (
        "http://example.test/logo.png",
        "https://example.test/logo.png",
        (REPO / "README.md").as_uri(),
    ):
        try:
            fetcher.fetch(url)
        except ValueError:
            continue
        raise AssertionError(f"fetched {url}")


def test_committed_palette_matches_global_css():
    """The certificate reads the site's colours: the committed module
    is exactly global.css's --color-* tokens."""
    tokens = dict(
        re.findall(r"--color-([a-z-]+):\s*(#[0-9a-fA-F]+)", GLOBAL_CSS.read_text())
    )
    assert tokens == PALETTE
    assert "accent" in PALETTE and "accent-contrast" in PALETTE


def test_committed_brand_assets_are_what_sync_brand_writes():
    """033: sync_brand.py is the one writer of palette.py, logo.png, and
    mark.png (and of every frontend icon); `--check` refuses a drift.
    Run the way the pre-changelog lint line runs it."""
    result = subprocess.run(
        [sys.executable, str(REPO / "frontend" / "scripts" / "sync_brand.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "in sync" in result.stdout
    assert not (BRAND_DIR / "monogram.svg").exists()
    for token in ("brand-blue", "brand-navy", "brand-teal", "accent"):
        assert token in PALETTE


def test_sample_snapshot_has_exactly_the_real_snapshot_keys(db_session):
    _, enrollment, _ = make_completed(db_session)
    profile = sponsor_service.get_profile(db_session)
    sample = certificates.sample_snapshot(
        profile, sponsor_service.get_state_registrations(db_session)
    )
    assert set(sample) == set(enrollment.completion.certificate_snapshot)
    assert sample["participant_name"] == "Sample Participant"
    assert sample["national_registry_id"] is None  # not registered


# --- 032: the admin preview -----------------------------------------------


PREVIEW_URL = "/api/v1/admin/sponsor/certificate-preview.pdf"


def test_preview_is_admin_only(client, db_session):
    assert client.get(PREVIEW_URL).status_code == 401
    make_account(
        db_session, "p@supercpe.test", PARTICIPANT_PASSWORD, "participant"
    )
    login(client, "p@supercpe.test", PARTICIPANT_PASSWORD)
    assert client.get(PREVIEW_URL).status_code == 403


def test_preview_renders_a_sample_and_stores_nothing(
    client, admin_headers, db_session, storage_root
):
    complete_profile(db_session)
    response = client.get(PREVIEW_URL, headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    text = pdf_text(response.content)
    assert "Sample Participant" in text
    assert "Sample Course Title" in text
    assert "superCPE" in text
    assert "Authorized by RYZE.AI LLC" in text
    assert "Certificate of Completion" in text
    assert "National Registry" not in text  # not registered
    assert len(PdfReader(BytesIO(response.content)).pages) == 1
    assert len(raster_images(response.content)) == 2  # the brand logo and seal

    assert db_session.query(Completion).count() == 0
    assert list(storage_root.rglob("*.pdf")) == []


def test_preview_respects_may_claim_registry(client, admin_headers, db_session):
    complete_profile(db_session)
    profile = sponsor_service.get_profile(db_session)
    profile.registry_status = "registered"
    profile.national_registry_id = "112233"
    db_session.commit()
    sponsor_service.set_state_registrations(
        db_session,
        [{"state": "NH", "registration_number": "NH-42", "notes": ""}],
    )
    text = pdf_text(client.get(PREVIEW_URL, headers=admin_headers).content)
    assert "National Registry of CPE Sponsors ID: 112233" in text
    assert "NH sponsor registration number: NH-42" in text


def test_preview_and_real_certificate_carry_the_uploaded_logo(
    client, admin_headers, db_session, storage_root
):
    """The mark comes from the profile at render time, for the preview
    and for a real certificate alike; clearing it brings the brand logo
    back for the next render — and never touches a stored PDF."""
    complete_profile(db_session)
    upload = client.put(
        "/api/v1/admin/sponsor/logo",
        headers=admin_headers,
        files={"file": ("logo.png", png_logo(64, 32), "image/png")},
    )
    assert upload.status_code == 200, upload.json()
    assert (64, 32) in raster_images(client.get(PREVIEW_URL, headers=admin_headers).content)

    _, enrollment, _ = make_completed_without_profile(db_session)
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    download = client.get(
        f"/api/v1/my/completions/{enrollment.completion.id}/certificate.pdf"
    )
    assert download.status_code == 200
    assert (64, 32) in raster_images(download.content)
    stored = (storage_root / enrollment.completion.certificate_key).read_bytes()

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.delete("/api/v1/admin/sponsor/logo").status_code == 200
    assert (64, 32) not in raster_images(client.get(PREVIEW_URL).content)
    # The issued certificate is not re-rendered.
    assert (storage_root / enrollment.completion.certificate_key).read_bytes() == stored
