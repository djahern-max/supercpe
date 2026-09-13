"""Generate every superCPE identity asset from the palette and the words.

The icon is `frontend/public/favicon.svg` — a Flaticon-licensed graphic
whose license permits use as a favicon and forbids use as a logo or
trademark. So it appears in the favicon, the apple-touch icon, and the
manifest icons, and nowhere else: not on a page, not on the OG card, not
on a certificate or in an email. Colors come from src/styles/global.css
and the words from site.config.json.

Run from the repo root with the backend venv's Python (Pillow ships with
it as fpdf2's dependency; the DejaVu faces are the certificate fonts).
Rasterizing the SVG uses macOS `sips`, which is on every Mac:

    backend/.venv/bin/python frontend/scripts/generate_identity.py

Reads:
    frontend/public/favicon.svg                (served as-is: the SVG favicon)
Writes:
    frontend/public/favicon.ico                (16, 32, 48 — legacy fallback)
    frontend/public/apple-touch-icon.png       (180px, opaque white, padded)
    frontend/public/icon-192.png, icon-512.png (manifest icons, transparent)
    frontend/public/og.png                     (1200x630 link-preview card:
                                                the wordmark alone, no icon)
    frontend/public/site.webmanifest
    backend/app/assets/brand/palette.py        (032: every --color-* token
                                                as a Python dict, so the
                                                certificate and the site
                                                read one palette)
    backend/app/assets/brand/monogram.svg      (032: the "sC" monogram the
                                                certificate falls back to
                                                when no sponsor logo is
                                                uploaded — glyph outlines
                                                from DejaVu Sans Bold on a
                                                rounded accent square, so it
                                                is drawn as code, needs no
                                                font at render time, and is
                                                not the Flaticon icon, whose
                                                license forbids logo use)

The backend never imports from frontend/; the two brand files are
committed and `backend/tests/test_certificates.py` checks they match
what this script would write, so the site and the certificate cannot
drift apart silently.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

FRONTEND = Path(__file__).resolve().parent.parent
PUBLIC = FRONTEND / "public"
FONTS = FRONTEND.parent / "backend" / "app" / "assets" / "fonts"
BRAND = FRONTEND.parent / "backend" / "app" / "assets" / "brand"

SITE = json.loads((FRONTEND / "site.config.json").read_text())
CSS = (FRONTEND / "src" / "styles" / "global.css").read_text()


def css_color(name: str) -> str:
    return re.search(rf"--color-{name}:\s*(#[0-9a-fA-F]+)", CSS)[1]


def css_palette() -> dict[str, str]:
    """Every `--color-*` token in global.css, in file order."""
    return dict(re.findall(r"--color-([a-z-]+):\s*(#[0-9a-fA-F]+)", CSS))


ACCENT = css_color("accent")
BG = css_color("bg")
TEXT = css_color("text")

BOLD = str(FONTS / "DejaVuSans-Bold.ttf")

# Rasterize once, large, and downscale: every small render comes from
# the same master, so the sizes agree with each other.
MASTER_SIZE = 1024
# iOS composites the touch icon over black where it is transparent, so
# it gets an opaque white ground with the mark inset by this fraction
# on every side.
TOUCH_PADDING = 0.12

WRITTEN = (
    "favicon.ico",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "og.png",
    "site.webmanifest",
)
BRAND_WRITTEN = ("palette.py", "monogram.svg")

# The certificate monogram: the letters, the square, and how much of the
# square the letters fill.
MONOGRAM_TEXT = "sC"
MONOGRAM_SIZE = 256
MONOGRAM_RADIUS = 48
MONOGRAM_FILL = 0.56


def rasterize_svg(svg: Path, size: int) -> Image.Image:
    if shutil.which("sips") is None:
        sys.exit("needs macOS `sips` (or install rsvg-convert and adapt)")
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "master.png"
        subprocess.run(
            ["sips", "-s", "format", "png", "-z", str(size), str(size),
             str(svg), "--out", str(png)],
            check=True,
            capture_output=True,
        )
        return Image.open(png).convert("RGBA").copy()


def mark(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


def touch_icon(master: Image.Image, size: int) -> Image.Image:
    inner = round(size * (1 - 2 * TOUCH_PADDING))
    image = Image.new("RGBA", (size, size), "#ffffff")
    inset = mark(master, inner)
    offset = (size - inner) // 2
    image.paste(inset, (offset, offset), inset)
    return image.convert("RGB")


def og_image() -> Image.Image:
    """The 1200x630 link-preview card: the wordmark on the site
    background and nothing else — no icon (the license), no tagline
    (nothing a scraper could mistake for a course fact)."""
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    name_font = ImageFont.truetype(BOLD, 120)
    draw.text(
        (width / 2, height / 2), SITE["name"], font=name_font, fill=TEXT, anchor="mm"
    )
    return image


def webmanifest() -> str:
    return (
        json.dumps(
            {
                "name": SITE["name"],
                "short_name": SITE["name"],
                "icons": [
                    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                ],
                "theme_color": ACCENT,
                "background_color": BG,
                "display": "browser",
            },
            indent=2,
        )
        + "\n"
    )


def palette_module() -> str:
    """backend/app/assets/brand/palette.py: the tokens as a dict, so the
    certificate CSS (`var(--color-accent)` and friends) reads the very
    values the site does."""
    lines = [
        '"""GENERATED by frontend/scripts/generate_identity.py from',
        "frontend/src/styles/global.css — do not edit by hand. The site's",
        "colour tokens, so the certificate (032) renders in the site's palette",
        "and cannot drift from it (pinned by test_certificates.py).",
        '"""',
        "",
        "PALETTE = {",
    ]
    for name, value in css_palette().items():
        lines.append(f'    "{name}": "{value}",')
    lines.append("}")
    return "\n".join(lines) + "\n"


def monogram_svg() -> str:
    """The "sC" monogram as pure paths: the glyph outlines are lifted from
    DejaVu Sans Bold with fontTools, so the SVG carries no text element
    and needs no font wherever it is drawn."""
    font = TTFont(BOLD)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    glyphs = []
    advance = 0
    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")
    for character in MONOGRAM_TEXT:
        glyph = glyph_set[cmap[ord(character)]]
        pen = SVGPathPen(glyph_set, ntos=lambda value: f"{value:g}")
        glyph.draw(pen)
        bounds = BoundsPen(glyph_set)
        glyph.draw(bounds)
        left, bottom, right, top = bounds.bounds
        x_min = min(x_min, advance + left)
        x_max = max(x_max, advance + right)
        y_min = min(y_min, bottom)
        y_max = max(y_max, top)
        glyphs.append((advance, pen.getCommands()))
        advance += glyph.width

    width = x_max - x_min
    height = y_max - y_min
    scale = MONOGRAM_SIZE * MONOGRAM_FILL / max(width, height)
    left = (MONOGRAM_SIZE - width * scale) / 2
    top = (MONOGRAM_SIZE - height * scale) / 2
    # Font units are y-up; scale(s, -s) flips them, so the translation
    # places the glyph box's top-left at (left, top).
    transform = (
        f"translate({left - scale * x_min:.3f} {top + scale * y_max:.3f}) "
        f"scale({scale:.5f} {-scale:.5f})"
    )
    paths = "".join(
        f'<path transform="translate({offset} 0)" d="{d}"/>'
        for offset, d in glyphs
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {MONOGRAM_SIZE} {MONOGRAM_SIZE}" '
        f'width="{MONOGRAM_SIZE}" height="{MONOGRAM_SIZE}">'
        f"<title>{SITE['name']}</title>"
        f'<rect width="{MONOGRAM_SIZE}" height="{MONOGRAM_SIZE}" '
        f'rx="{MONOGRAM_RADIUS}" fill="{ACCENT}"/>'
        f'<g fill="{css_color("accent-contrast")}" transform="{transform}">'
        f"{paths}</g></svg>\n"
    )


def write_brand() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    (BRAND / "palette.py").write_text(palette_module())
    (BRAND / "monogram.svg").write_text(monogram_svg())
    for name in BRAND_WRITTEN:
        print(f"wrote {(BRAND / name).relative_to(FRONTEND.parent)}")


def main() -> None:
    write_brand()
    master = rasterize_svg(PUBLIC / "favicon.svg", MASTER_SIZE)
    mark(master, 512).save(PUBLIC / "icon-512.png")
    mark(master, 192).save(PUBLIC / "icon-192.png")
    touch_icon(master, 180).save(PUBLIC / "apple-touch-icon.png")
    mark(master, 48).save(
        PUBLIC / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[mark(master, 32), mark(master, 16)],
    )
    og_image().save(PUBLIC / "og.png")
    (PUBLIC / "site.webmanifest").write_text(webmanifest())
    for name in WRITTEN:
        print(f"wrote {(PUBLIC / name).relative_to(FRONTEND)}")


if __name__ == "__main__":
    main()
