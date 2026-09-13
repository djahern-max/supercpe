"""Certificate of completion rendering (9.01).

`render` takes the frozen `certificate_snapshot` dict and nothing else —
deliberately no db session — so a certificate can only ever print what was
true when the credit was earned. Re-rendering the same snapshot produces
the same text content (asserted by test); byte identity is not required
(the PDF carries a creation timestamp in its metadata).

032: the page is an HTML template (app/templates/certificate.html) with
its CSS beside it, filled by Jinja2 and laid out by WeasyPrint. Layout
is CSS; the palette is the site's own (app/assets/brand/palette.py,
written by frontend/scripts/sync_brand.py from global.css); the mark at
the top is the uploaded sponsor logo when the caller passes one, else
the superCPE brand logo (033: app/assets/brand/logo.png, derived from
brand/ by the same script — the sponsor *is* superCPE, LLC, so the brand
mark is the sponsor mark). The brand mark also sits behind the award as
a faint seal. The logo is presentation, not a Section 9 fact: it is an
optional argument, never a snapshot key, and a stored PDF is never
re-rendered. The vendored DejaVu Sans faces (011, license alongside them
in app/assets/fonts/) are declared with @font-face, so a participant
named "Nguyễn" or "Michałowski" still gets their own name.

Nothing is fetched at render time: the URL fetcher below admits only
data: URIs and files under app/assets/ (the brand images and the fonts),
so an uploaded SVG that points at the network draws without that
reference. The PDF's creation date is the snapshot's completion instant,
never the clock, so two renders of one snapshot are byte-identical and
the stored-once invariant (9.02) can be checked by comparison.
"""

import base64
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse
from urllib.request import url2pathname

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher

from app.assets.brand.palette import PALETTE
from app.constants.certificate import PROGRAM_TYPE, TIME_STATEMENT
from app.constants.credit import CREDIT_BASIS

_APP_DIR = Path(__file__).resolve().parent.parent
_ASSETS_DIR = _APP_DIR / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"
_TEMPLATES_DIR = _APP_DIR / "templates"
_BRAND_DIR = _ASSETS_DIR / "brand"
BRAND_LOGO_PATH = _BRAND_DIR / "logo.png"
BRAND_MARK_PATH = _BRAND_DIR / "mark.png"

# 019's public verification page resolves the code. The path deliberately
# avoids 017's /verify (email verification). Stored PDFs are immutable,
# so certificates rendered before 019 keep their old line while their
# codes still verify.
VERIFY_PATH = "supercpe.com/certificates/verify"

log = logging.getLogger("app.certificates")

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


class Logo(NamedTuple):
    """An uploaded sponsor mark: the bytes and their media type
    (image/png or image/svg+xml)."""

    content: bytes
    media_type: str


class RendererUnavailable(RuntimeError):
    """WeasyPrint could not lay out a trivial page — the Pango stack the
    Dockerfile installs is missing or broken. A boot refusal, like a
    missing ffprobe (002), so the failure is a failed deploy, not a
    participant's first download."""


def render(snapshot: dict, logo: Logo | None = None) -> bytes:
    """One page from the snapshot dict: the eleven 9.01 items in reading
    order. Item 5 (location) prints as not applicable for self study; item
    8 prints only when the snapshot carries it."""
    return _to_pdf(render_html(snapshot, logo))


def render_html(snapshot: dict, logo: Logo | None = None) -> str:
    """The filled template, before layout. Exposed so tests can see the
    mark the PDF was drawn from."""
    return _env.get_template("certificate.html").render(_context(snapshot, logo))


def _context(snapshot: dict, logo: Logo | None) -> dict:
    """Exactly the snapshot keys the certificate prints, plus the mark
    and the palette. Nothing here reads a live table."""
    people = []
    if snapshot["developed_by"]:
        people.append(f"Developed by {_person(snapshot['developed_by'])}")
    if snapshot["reviewed_by"]:
        people.append(f"Reviewed by {_person(snapshot['reviewed_by'])}")
    return {
        "palette": PALETTE,
        "mark_src": mark_src(logo),
        "seal_src": BRAND_MARK_PATH.as_uri(),
        # WeasyPrint's dcterms.created → the PDF's /CreationDate: the
        # completion instant from the snapshot, so the bytes carry no clock.
        "created": snapshot["completed_at"],
        "sponsor_name": snapshot["sponsor_name"],  # item 1
        # 9.01.1: the awarding entity. Issuance never lets legal_name be
        # blank; the fallback only matters for a preview of a bare profile.
        "awarding_entity": snapshot["sponsor_legal_name"] or snapshot["sponsor_name"],
        "participant": snapshot["participant_name"] or snapshot["participant_email"],
        "course_title": snapshot["course_title"],  # item 3
        "course_code": snapshot["course_code"],
        "completed_on": snapshot["completed_at"][:10],  # item 4
        "program_type": snapshot["program_type"],  # item 6
        "credit": snapshot["credit"],  # item 7
        "field_of_study": snapshot["field_of_study"],  # item 7
        "time_statement": snapshot["time_statement"],  # item 10
        "national_registry_id": snapshot["national_registry_id"],  # item 8
        "state_registrations": snapshot["state_registrations"],  # item 9
        "other_statements": snapshot["other_statements"],  # item 11
        "people": ". ".join(people) + "." if people else "",
        "certificate_number": snapshot["certificate_number"],
        "verification_token": snapshot["verification_token"],
    }


def mark_src(logo: Logo | None) -> str:
    """The `<img src>` for the mark at the top: the uploaded logo as a
    data: URI (the template never references storage), else the brand
    logo as a file: URL under app/assets/brand/, which the fetcher
    admits."""
    if logo is None:
        return BRAND_LOGO_PATH.as_uri()
    encoded = base64.b64encode(logo.content).decode("ascii")
    return f"data:{logo.media_type};base64,{encoded}"


class _AssetsOnlyFetcher(URLFetcher):
    """WeasyPrint's URL fetcher, narrowed: data: URIs, and files under
    app/assets/ (the @font-face sources and the brand images). Anything
    else — an uploaded SVG's external image, a stray http reference — is
    refused, and WeasyPrint draws on without it."""

    def __init__(self):
        super().__init__(allowed_protocols={"data", "file"})

    def fetch(self, url, headers=None):
        if url.startswith("file:"):
            path = Path(url2pathname(urlparse(url).path)).resolve()
            if not path.is_relative_to(_ASSETS_DIR):
                raise ValueError(
                    f"certificate rendering does not fetch {url[:80]!r}"
                )
        return super().fetch(url, headers)


def _to_pdf(html: str) -> bytes:
    font_config = FontConfiguration()
    fetcher = _AssetsOnlyFetcher()
    stylesheet = CSS(
        filename=str(_TEMPLATES_DIR / "certificate.css"),
        font_config=font_config,
        url_fetcher=fetcher,
    )
    document = HTML(
        string=html,
        base_url=str(_TEMPLATES_DIR / "certificate.html"),
        url_fetcher=fetcher,
    )
    return document.write_pdf(stylesheets=[stylesheet], font_config=font_config)


def sample_snapshot(profile, registrations) -> dict:
    """A snapshot for the admin preview (032): a fixed fake participant
    and course, today's date, and the sponsor's facts as they stand —
    item 8 gated on `may_claim_registry` exactly as `create` gates it.
    Same keys as a real snapshot (pinned by test) so the template sees
    no difference; nothing is stored."""
    return {
        "sponsor_name": profile.name,
        "sponsor_legal_name": profile.legal_name,
        "participant_name": "Sample Participant",
        "participant_email": "sample@example.test",
        "course_title": "Sample Course Title",
        "course_code": "SAMPLE",
        "completed_at": date.today().isoformat(),
        "location": None,
        "program_type": PROGRAM_TYPE,
        "credit": "1.0",
        "field_of_study": "Accounting",
        "national_registry_id": (
            profile.national_registry_id if profile.may_claim_registry else None
        ),
        "state_registrations": [
            {"state": row.state, "number": row.registration_number}
            for row in registrations
        ],
        "time_statement": TIME_STATEMENT,
        "other_statements": [
            line.strip()
            for line in profile.other_certificate_statements.splitlines()
            if line.strip()
        ],
        "knowledge_level": "Basic",
        "package_versions": {},
        "passing_pct": "70",
        "score_pct": "100",
        "recommended_credit_basis": CREDIT_BASIS,
        "developed_by": {"name": "Sample Developer", "credentials": "CPA"},
        "reviewed_by": {"name": "Sample Reviewer", "credentials": "CPA"},
        "certificate_number": "SAMPLE-000000",
        "verification_token": "sample-certificate-not-issued",
        "snapshot_version": 1,
    }


def ensure_renderer_available() -> None:
    """Boot and preflight check (the ffprobe pattern): lay out one trivial
    page. Raises RendererUnavailable naming the cause when the Pango
    stack is missing."""
    try:
        HTML(string="<p>ok</p>").write_pdf()
    except Exception as error:  # pragma: no cover - only on a broken image
        raise RendererUnavailable(
            "The certificate renderer (WeasyPrint) cannot lay out a page: "
            f"{error!r}. The api image installs libpango-1.0-0, "
            "libpangoft2-1.0-0 and libharfbuzz-subset0 (deploy/Dockerfile); "
            "a build without them cannot issue certificates and must not "
            "boot (Standards 9.01)."
        ) from error


@lru_cache(maxsize=1)
def renderer_check() -> str:
    """/health's `renderer` field. Cached per process: the stack is a
    property of the image, not of the moment, so the smoke render runs
    once, not on every probe."""
    try:
        ensure_renderer_available()
    except RendererUnavailable as error:
        log.error("renderer check failed: %s", error)
        return "error"
    return "ok"


def _person(person: dict) -> str:
    if person.get("credentials"):
        return f"{person['name']}, {person['credentials']}"
    return person["name"]
