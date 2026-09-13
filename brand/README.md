# superCPE brand assets

Assets created by Dane for superCPE, LLC. Owned outright; no third-party
license.

This directory is the one source of every brand asset the site and the
certificate show. Nothing in the app reads it directly: run
`frontend/scripts/sync_brand.py` (see `docs/OPERATIONS.md`, "Brand
assets (033)") and it derives every fixed-name file the frontend and the
backend need. Edit or replace files here, re-run the script, commit
everything it wrote. `sync_brand.py --check` fails when any derived file
is stale.

## Files and roles

| File | Role | Format | Notes |
|------|------|--------|-------|
| `supercpe-logo.png` | **Primary logo** (horizontal): site header, landing page, certificate top, JSON-LD `logo`, OG card | PNG, RGBA, 2172 × 724, transparent ground | The mark at left, "superCPE" wordmark at right. Artwork occupies (100, 103)–(2136, 706); the script crops to that box. |
| `supercpe-icon.png` | **Mark** (square): manifest icons, admin-nav mark, certificate seal | PNG, RGBA, 1338 × 1338, transparent ground | The open book with the teal check; no words. Artwork occupies (80, 90)–(1258, 1248). |
| `favicon.ico` | Legacy favicon | ICO holding 16, 32, and 48 px | Copied verbatim to `frontend/public/favicon.ico`. |
| `favicon-16x16.png`, `favicon-32x32.png` | PNG favicons | PNG 16 × 16 (palette), 32 × 32 (RGBA) | Copied verbatim to `frontend/public/`. |
| `apple-touch-icon.png` | iOS home-screen icon | PNG, RGBA, 180 × 180 | Copied verbatim to `frontend/public/apple-touch-icon.png`. Note: the ground is transparent; iOS composites transparent pixels over black. Supplying an opaque version here replaces it with one script run. |

Source format: raster only (PNG). No SVG was supplied. The largest
dimension is 2172 px (the logo) and 1338 px (the mark); every derived
raster is a downscale, never an upscale. There is no SVG favicon and no
vector copy for the certificate; both use PNGs derived at more than 2×
their rendered size.

Optional roles not supplied: wordmark alone, dark-background variants, an
OG-specific composition. The OG card is composed by the script (logo plus
the one line from `frontend/site.config.json`). No typeface was
specified, so the site keeps its system font stack and the certificate
keeps DejaVu Sans.

## Palette

No palette file was supplied. These values were sampled from the artwork
(the dominant opaque pixel of each region of `supercpe-icon.png` and
`supercpe-logo.png`) and are the ones `frontend/src/styles/global.css`
carries as the brand tokens:

| Token | Hex | Sampled from | Use |
|-------|-----|--------------|-----|
| `--color-brand-blue` | `#006afc` | Logo wordmark "CPE" and the right page of the book (`#006afc` in the logo, `#006ffc` in the icon; the logo's value is used) | Marks, borders, rules, filled buttons (white text on it: 4.70:1) |
| `--color-brand-navy` | `#012c6b` | Left page of the book, the word "super" | Headings, the certificate heading |
| `--color-brand-teal` | `#01b6af` | The check | Marks and borders only — 2.53:1 on white, never text |
| `--color-accent` | `#0066f4` | A tint of the brand blue | Link and accent text: 4.99:1 on white, 4.70:1 on the page ground. The brand blue itself is 4.70:1 on white but 4.42:1 on the page ground (`#f5f7fb`), under WCAG AA's 4.5:1 for body text, so text uses this tint and marks use the true blue. |

Confirmed against the artwork on 2026-09-13.
