"""Generate every superCPE identity asset from the palette and the words.

The mark is deliberately plain and regenerable: a rounded square in the
site's accent color carrying an "sC" monogram, drawn here in code — not
sourced from anywhere. Colors come from src/styles/global.css and the
words from site.config.json, so a rebrand is: edit those two files, run
this script, rebuild. Nothing else moves.

Run from the repo root with the backend venv's Python (Pillow ships with
it as fpdf2's dependency; the DejaVu faces are the certificate fonts):

    backend/.venv/bin/python frontend/scripts/generate_identity.py

Writes:
    frontend/src/assets/identity/favicon.svg   (hashed by Vite's build)
    frontend/public/favicon.ico                (32px legacy fallback)
    frontend/public/apple-touch-icon.png       (180px, fixed name)
    frontend/public/icon-192.png, icon-512.png (manifest icons)
    frontend/public/og.png                     (1200x630 link-preview card)
    frontend/public/site.webmanifest
"""

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FRONTEND = Path(__file__).resolve().parent.parent
FONTS = FRONTEND.parent / "backend" / "app" / "assets" / "fonts"

SITE = json.loads((FRONTEND / "site.config.json").read_text())
CSS = (FRONTEND / "src" / "styles" / "global.css").read_text()


def css_color(name: str) -> str:
    return re.search(rf"--color-{name}:\s*(#[0-9a-fA-F]+)", CSS)[1]


ACCENT = css_color("accent")
ACCENT_CONTRAST = css_color("accent-contrast")
BG = css_color("bg")
TEXT = css_color("text")
TEXT_MUTED = css_color("text-muted")

BOLD = str(FONTS / "DejaVuSans-Bold.ttf")
REGULAR = str(FONTS / "DejaVuSans.ttf")

MONOGRAM = "sC"


def draw_mark(size: int) -> Image.Image:
    """The rounded accent square with the monogram, drawn at 4x and
    downscaled so the small renders stay crisp."""
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = round(canvas * 0.22)
    draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius, fill=ACCENT)
    font = ImageFont.truetype(BOLD, round(canvas * 0.52))
    draw.text(
        (canvas / 2, canvas * 0.47),
        MONOGRAM,
        font=font,
        fill=ACCENT_CONTRAST,
        anchor="mm",
    )
    return image.resize((size, size), Image.LANCZOS)


def favicon_svg() -> str:
    # The same design as draw_mark, as markup: browsers render this one,
    # so it uses the site's own font stack with DejaVu's metrics cousins.
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n'
        f'  <rect width="64" height="64" rx="14" fill="{ACCENT}"/>\n'
        '  <text x="32" y="34" text-anchor="middle" dominant-baseline="central"\n'
        '        font-family="DejaVu Sans, -apple-system, BlinkMacSystemFont,'
        " 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif\"\n"
        f'        font-size="33" font-weight="bold" fill="{ACCENT_CONTRAST}">'
        f"{MONOGRAM}</text>\n"
        "</svg>\n"
    )


def og_image() -> Image.Image:
    """The 1200x630 link-preview card: mark, name, tagline, domain —
    nothing a scraper could mistake for course facts."""
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    mark = draw_mark(160)
    image.paste(mark, ((width - 160) // 2, 96), mark)

    name_font = ImageFont.truetype(BOLD, 96)
    tagline_font = ImageFont.truetype(REGULAR, 40)
    domain_font = ImageFont.truetype(BOLD, 30)
    center = width / 2
    draw.text((center, 356), SITE["name"], font=name_font, fill=TEXT, anchor="mm")
    draw.text(
        (center, 448), SITE["tagline"], font=tagline_font, fill=TEXT_MUTED, anchor="mm"
    )
    domain = SITE["origin"].removeprefix("https://")
    draw.text((center, 540), domain, font=domain_font, fill=ACCENT, anchor="mm")
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


def main() -> None:
    identity = FRONTEND / "src" / "assets" / "identity"
    identity.mkdir(parents=True, exist_ok=True)
    public = FRONTEND / "public"

    (identity / "favicon.svg").write_text(favicon_svg())
    draw_mark(512).save(public / "icon-512.png")
    draw_mark(192).save(public / "icon-192.png")
    draw_mark(180).save(public / "apple-touch-icon.png")
    draw_mark(32).save(public / "favicon.ico", sizes=[(32, 32)])
    og_image().save(public / "og.png")
    (public / "site.webmanifest").write_text(webmanifest())
    for path in sorted([*public.iterdir(), identity / "favicon.svg"]):
        print(f"wrote {path.relative_to(FRONTEND)}")


if __name__ == "__main__":
    main()
