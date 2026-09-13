"""Derive every fixed-name brand asset from brand/ (033).

`brand/` at the repo root holds the files Dane produced (see
brand/README.md for the roles). Nothing in the app reads that directory:
this script derives every copy the frontend and the backend need, so a
rebrand is one edit in brand/, one run here, one commit. It replaces
022's generate_identity.py, which drew a placeholder and rasterized a
Flaticon favicon whose license forbade logo use.

Run from the repo root with the backend venv's Python (Pillow arrives as
a WeasyPrint dependency; no SVG rasterizer is needed because every source
is a PNG):

    backend/.venv/bin/python frontend/scripts/sync_brand.py          # write
    backend/.venv/bin/python frontend/scripts/sync_brand.py --check  # exit 1 if stale

Reads:
    brand/supercpe-logo.png                    (primary logo, horizontal)
    brand/supercpe-icon.png                    (the square mark)
    brand/favicon.ico, favicon-16x16.png,
    brand/favicon-32x32.png, apple-touch-icon.png  (copied verbatim)
    frontend/site.config.json                  (the name and the one line)
    frontend/src/styles/global.css             (the --color-* tokens)
Writes:
    frontend/public/favicon.ico, favicon-16x16.png, favicon-32x32.png,
    frontend/public/apple-touch-icon.png       (verbatim copies)
    frontend/public/icon-192.png, icon-512.png (manifest icons: the mark
                                                on an opaque white ground,
                                                inset so a maskable crop
                                                keeps it whole)
    frontend/public/logo.png                   (the primary logo; JSON-LD)
    frontend/public/og.png                     (1200x630 link-preview card:
                                                the logo and the one line
                                                from site.config.json)
    frontend/public/site.webmanifest
    frontend/src/assets/brand/logo.png         (the same logo, on Vite's
                                                hashed pipeline: the site
                                                header and the landing page)
    frontend/src/assets/brand/mark.png         (the mark for the admin nav)
    backend/app/assets/brand/logo.png          (the certificate's top mark)
    backend/app/assets/brand/mark.png          (the certificate's seal)
    backend/app/assets/brand/palette.py        (every --color-* token as a
                                                dict, so the certificate
                                                and the site read one
                                                palette)

Every output is a pure function of the inputs, so a second run is
byte-identical and `--check` can compare. The backend never imports from
frontend/, and the api image copies backend/ only, which is why the
backend gets its own copies.
"""

import json
import re
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent.parent
BRAND = REPO / "brand"
FRONTEND = REPO / "frontend"
PUBLIC = FRONTEND / "public"
SRC_BRAND = FRONTEND / "src" / "assets" / "brand"
BACKEND_BRAND = REPO / "backend" / "app" / "assets" / "brand"
FONTS = REPO / "backend" / "app" / "assets" / "fonts"

SITE = json.loads((FRONTEND / "site.config.json").read_text())
CSS = (FRONTEND / "src" / "styles" / "global.css").read_text()

LOGO_SOURCE = BRAND / "supercpe-logo.png"
MARK_SOURCE = BRAND / "supercpe-icon.png"
VERBATIM = (
    "favicon.ico",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "apple-touch-icon.png",
)

# The logo is written once at this width and copied to its three homes.
# At 800 px it is more than 2x the widest place it is drawn (the landing
# page at 360 CSS px; the certificate at 170 pt) and a few dozen KB.
LOGO_WIDTH = 800
# The admin nav draws the mark at 28 px; the certificate seal at 200 pt.
NAV_MARK_SIZE = 128
SEAL_MARK_SIZE = 512
# Manifest icons: Android masks to a circle of 80% diameter, so the
# artwork must sit inside the central 64% square to survive every mask.
ICON_INSET = 0.64
OG_SIZE = (1200, 630)
OG_LOGO_WIDTH = 720
OG_LINE_SIZE = 44


def css_palette() -> dict[str, str]:
    """Every `--color-*` token in global.css, in file order."""
    return dict(re.findall(r"--color-([a-z-]+):\s*(#[0-9a-fA-F]+)", CSS))


def cropped(source: Path) -> Image.Image:
    """The artwork alone: the source with its transparent margin cut off."""
    image = Image.open(source).convert("RGBA")
    return image.crop(image.getchannel("A").getbbox())


def logo(width: int) -> Image.Image:
    art = cropped(LOGO_SOURCE)
    height = round(art.height * width / art.width)
    return art.resize((width, height), Image.LANCZOS)


def mark(size: int, inset: float = 1.0, ground: str | None = None) -> Image.Image:
    """The mark centred on a size x size canvas — transparent, or on an
    opaque `ground` — with its longest side at `inset` of the canvas."""
    art = cropped(MARK_SOURCE)
    longest = round(size * inset)
    scale = longest / max(art.size)
    art = art.resize(
        (max(1, round(art.width * scale)), max(1, round(art.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), ground or (0, 0, 0, 0))
    canvas.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
    return canvas.convert("RGB") if ground else canvas


def og_card(palette: dict[str, str]) -> Image.Image:
    """The link-preview card: the logo and the one line from
    site.config.json on the surface colour. Nothing else — no course
    fact, no Registry word, nothing a scraper could take for a claim."""
    width, height = OG_SIZE
    card = Image.new("RGB", (width, height), palette["surface"])
    art = logo(OG_LOGO_WIDTH)
    line_font = ImageFont.truetype(str(FONTS / "DejaVuSans-Bold.ttf"), OG_LINE_SIZE)
    gap = 56
    block_height = art.height + gap + OG_LINE_SIZE
    top = (height - block_height) // 2
    card.paste(art, ((width - art.width) // 2, top), art)
    ImageDraw.Draw(card).text(
        (width / 2, top + art.height + gap + OG_LINE_SIZE / 2),
        SITE["description"],
        font=line_font,
        fill=palette["brand-navy"],
        anchor="mm",
    )
    return card


def webmanifest(palette: dict[str, str]) -> str:
    return (
        json.dumps(
            {
                "name": SITE["name"],
                "short_name": SITE["name"],
                "icons": [
                    {
                        "src": "/icon-192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                        "purpose": "any maskable",
                    },
                    {
                        "src": "/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "any maskable",
                    },
                ],
                "theme_color": palette["accent"],
                "background_color": palette["bg"],
                "display": "browser",
            },
            indent=2,
        )
        + "\n"
    )


def palette_module(palette: dict[str, str]) -> str:
    """backend/app/assets/brand/palette.py: the tokens as a dict, so the
    certificate CSS (`var(--color-accent)` and friends) reads the very
    values the site does."""
    lines = [
        '"""GENERATED by frontend/scripts/sync_brand.py from',
        "frontend/src/styles/global.css — do not edit by hand. The site's",
        "colour tokens, so the certificate renders in the site's palette and",
        "cannot drift from it (sync_brand.py --check refuses a stale copy).",
        '"""',
        "",
        "PALETTE = {",
    ]
    for name, value in palette.items():
        lines.append(f'    "{name}": "{value}",')
    lines.append("}")
    return "\n".join(lines) + "\n"


def png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def outputs() -> dict[Path, bytes]:
    """Every derived file and its bytes, computed from brand/ alone."""
    palette = css_palette()
    for token in ("surface", "bg", "accent", "brand-navy"):
        if token not in palette:
            sys.exit(f"global.css has no --color-{token} token")
    logo_png = png(logo(LOGO_WIDTH))
    files: dict[Path, bytes] = {}
    for name in VERBATIM:
        files[PUBLIC / name] = (BRAND / name).read_bytes()
    files[PUBLIC / "icon-192.png"] = png(mark(192, ICON_INSET, palette["surface"]))
    files[PUBLIC / "icon-512.png"] = png(mark(512, ICON_INSET, palette["surface"]))
    files[PUBLIC / "logo.png"] = logo_png
    files[PUBLIC / "og.png"] = png(og_card(palette))
    files[PUBLIC / "site.webmanifest"] = webmanifest(palette).encode()
    files[SRC_BRAND / "logo.png"] = logo_png
    files[SRC_BRAND / "mark.png"] = png(mark(NAV_MARK_SIZE))
    files[BACKEND_BRAND / "logo.png"] = logo_png
    files[BACKEND_BRAND / "mark.png"] = png(mark(SEAL_MARK_SIZE))
    files[BACKEND_BRAND / "palette.py"] = palette_module(palette).encode()
    return files


def main(argv: list[str]) -> int:
    missing = [name for name in (LOGO_SOURCE.name, MARK_SOURCE.name, *VERBATIM)
               if not (BRAND / name).exists()]
    if missing:
        sys.exit(f"brand/ is missing {', '.join(missing)} — see brand/README.md")
    files = outputs()
    if argv == ["--check"]:
        stale = [
            path for path, content in files.items()
            if not path.exists() or path.read_bytes() != content
        ]
        for path in stale:
            print(f"stale: {path.relative_to(REPO)}")
        if stale:
            print("run frontend/scripts/sync_brand.py and commit the result")
            return 1
        print(f"brand assets in sync ({len(files)} files)")
        return 0
    if argv:
        sys.exit("usage: sync_brand.py [--check]")
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"wrote {path.relative_to(REPO)} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
