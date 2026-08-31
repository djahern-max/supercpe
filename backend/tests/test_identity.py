"""Feature 022: site identity and link previews.

The OG/meta tags are static and site-wide in frontend/index.html (a Vite
SPA; scrapers run no JavaScript), so the standing content rules apply to
that one file: no course facts (the 015/021 restraint — link, don't
restate) and no Registry words. These tests read the frontend sources the
way the build does — index.html's %SITE_*% tokens filled from
site.config.json — and hold the rendered result to the rules. The
sitemap half exercises the one new intentionally-public API route."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from app.services import site as site_service
from tests.test_enrollments import make_published_course
from tests.test_site import open_the_site

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
PUBLIC = FRONTEND / "public"

SITEMAP_URL = "/api/v1/sitemap.xml"
LOC = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"


def rendered_index_html() -> str:
    """index.html exactly as vite.config.js's site-meta plugin emits it:
    every token filled from site.config.json and the accent color from
    global.css."""
    site = json.loads((FRONTEND / "site.config.json").read_text())
    accent = re.search(
        r"--color-accent:\s*(#[0-9a-fA-F]+)",
        (FRONTEND / "src" / "styles" / "global.css").read_text(),
    )[1]
    html = (FRONTEND / "index.html").read_text()
    html = (
        html.replace("%SITE_ORIGIN%", site["origin"])
        .replace("%SITE_NAME%", site["name"])
        .replace("%SITE_TITLE%", f"{site['name']} — {site['tagline']}")
        .replace("%SITE_DESCRIPTION%", site["description"])
        .replace("%SITE_THEME_COLOR%", accent)
    )
    assert "%SITE_" not in html, "an index.html token has no replacement"
    return html


# --- the metadata ----------------------------------------------------------


def test_index_html_obeys_the_content_rules():
    """Site-wide metadata describes the sponsor, never the course: no
    Registry words, no credit figure, no QAS, no price — the same rules
    the 015 landing page and the 021 invitation hold to."""
    html = rendered_index_html()
    assert "National Registry" not in html
    assert "national_registry" not in html
    assert "QAS" not in html
    assert not re.search(r"\d+(\.\d+)?\s*(CPE|credit|hour)", html, re.I)
    assert not re.search(r"\$\s*\d", html)


def test_index_html_carries_the_full_tag_set():
    site = json.loads((FRONTEND / "site.config.json").read_text())
    html = rendered_index_html()

    def content_of(attr, name):
        match = re.search(rf'{attr}="{name}" content="([^"]+)"', html)
        assert match, f"missing {name}"
        return match[1]

    assert re.search(r"<title>[^<]+</title>", html)
    assert content_of("name", "description")
    assert content_of("property", "og:type") == "website"
    assert content_of("property", "og:site_name") == site["name"]
    assert content_of("property", "og:title")
    assert content_of("property", "og:description")
    assert content_of("property", "og:url") == f"{site['origin']}/"
    assert content_of("name", "twitter:card") == "summary_large_image"
    assert content_of("name", "theme-color").startswith("#")
    # Scrapers resolve nothing: the image and canonical are absolute.
    og_image = content_of("property", "og:image")
    assert og_image == f"{site['origin']}/og.png"
    assert og_image.startswith("https://")
    assert f'<link rel="canonical" href="{site["origin"]}/" />' in html


def test_index_html_json_ld_is_valid_and_minimal():
    """The Organization block claims nothing it can't back: name, url,
    logo, and no other properties."""
    html = rendered_index_html()
    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    assert match
    block = json.loads(match[1])
    assert set(block) == {"@context", "@type", "name", "url", "logo"}
    assert block["@type"] == "Organization"


def test_identity_assets_replace_every_vite_default():
    html = rendered_index_html()
    assert "vite.svg" not in html
    # The SVG favicon is hashed by the build (it lives in src/); the
    # fixed-name files scrapers and old browsers fetch blindly live in
    # public/ — including og.png, whose URL is baked into a static tag.
    assert (FRONTEND / "src" / "assets" / "identity" / "favicon.svg").exists()
    assert not (PUBLIC / "favicon.svg").exists(), "the Vite default is back"
    for name in (
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "og.png",
        "site.webmanifest",
        "robots.txt",
    ):
        assert (PUBLIC / name).exists(), name


def test_webmanifest_names_the_site_and_both_icons():
    manifest = json.loads((PUBLIC / "site.webmanifest").read_text())
    site = json.loads((FRONTEND / "site.config.json").read_text())
    assert manifest["name"] == site["name"]
    assert manifest["theme_color"].startswith("#")
    assert [icon["sizes"] for icon in manifest["icons"]] == [
        "192x192",
        "512x512",
    ]


def test_robots_allows_all_but_admin_and_names_the_sitemap():
    robots = (PUBLIC / "robots.txt").read_text()
    assert "User-agent: *" in robots
    assert "Disallow: /admin" in robots
    # Allow everything else: no bare disallow-all line.
    assert not re.search(r"^Disallow: /\s*$", robots, re.M)
    site = json.loads((FRONTEND / "site.config.json").read_text())
    assert f"Sitemap: {site['origin']}/sitemap.xml" in robots


# --- the sitemap -----------------------------------------------------------


def sitemap_locs(client) -> list[str]:
    response = client.get(SITEMAP_URL)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    return [loc.text for loc in ET.fromstring(response.text).iter(LOC)]


def test_sitemap_while_coming_soon_lists_only_the_root(client):
    origin = site_service.site_origin()
    assert sitemap_locs(client) == [f"{origin}/"]


def test_sitemap_at_open_lists_the_public_set_published_courses_only(
    client, db_session, admin_account, admin_headers
):
    make_published_course(db_session, "GOLD")
    # A second course exists but is not published: it must not be listed.
    from tests.test_enrollments import make_publish_ready_course

    make_publish_ready_course(db_session, "SILV")
    open_the_site(client)
    client.cookies.clear()

    origin = site_service.site_origin()
    assert sitemap_locs(client) == [
        f"{origin}/",
        f"{origin}/courses",
        f"{origin}/courses/GOLD",
        f"{origin}/policies",
        f"{origin}/certificates/verify",
        f"{origin}/register",
    ]
