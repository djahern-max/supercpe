# Current Feature

## Feature 033 — Brand assets: one source, used everywhere

> Confirm 032 against the last entry in `CHANGELOG.md` before starting.
> This supersedes the earlier 032 draft (certificate-only, "sC" monogram
> for now). 031 (player seeking) may or may not have shipped; nothing
> here depends on it.
>
> **Stop before Task 1 if `brand/` at the repo root does not exist or is
> empty.** Dane places the brand files there by hand; this feature does
> not draw a logo.

## Goal

superCPE has real brand assets. They live in one committed place, are
copied to the places that need them by one script, and appear on every
surface that shows the sponsor's face: the browser tab and home-screen
icons, the link-preview card, the site header, the coming-soon landing
page, and the certificate. The certificate is rendered from an HTML
template to PDF instead of drawn primitive by primitive. The admin
navigation works on a phone.

Nothing about what any surface *says* changes. The landing page still
discloses no course fact; the certificate still prints every 9.01 item
from the snapshot alone; no surface gains a Registry claim or mark.

## Why

022 generated a placeholder "sC" monogram from a script because no brand
existed. The current `favicon.svg` is a Flaticon download — licensed for
use with attribution, not as a company mark — so it has stayed off the
certificate. Dane has now produced the assets. The certificate is the one
artifact a participant keeps and hands to a state board or employer; the
landing page is the only public surface until opening day; the admin nav
is used from a phone on job sites. All four are branding work on the same
files, so they ship together.

## In scope

1. `brand/` source directory + sync script that derives every fixed-name
   asset from it (replaces 022's `generate_identity.py`).
2. Favicon set, manifest icons, apple-touch-icon, `og.png`, JSON-LD logo.
3. Site header wordmark → brand logo image; `global.css` palette aligned
   to the brand colors.
4. Landing page (`ComingSoon`) redesigned around the assets.
5. Certificate PDF rendered from an HTML/CSS template with the brand mark.
6. `AdminNav` responsive below tablet width; `SiteHeader` verified at the
   same widths and fixed if it also overflows.
7. OPERATIONS.md "Site identity" section rewritten for the new source.

## Out of scope — flag, don't build

- Any new logo, mark, or color Claude Code would have to invent. If a
  needed role (see Task 1) has no file in `brand/`, stop and report.
- The NASBA Registry logo. Not licensed to superCPE; `may_claim_registry`
  is false. Belongs to no asset, template, or page.
- Per-course OG cards (needs SSR — 022 ROADMAP note stands).
- A `logo_path` on `sponsor_profile`. The sponsor *is* superCPE, LLC; the
  brand mark is the sponsor mark. A per-sponsor slot returns if a second
  sponsor ever exists (001 decision).
- Re-rendering already-issued certificates. Stored once, never
  regenerated (011). All production data is test data pre-launch; old
  PDFs keeping the old look is expected.
- Landing-page copy. Keep the existing words unless Dane supplies new
  ones; see Open question 1.
- The open-mode root page. Recon what SiteGate serves at `/` when
  `site_mode = open`; if it is the catalog or a redirect, leave it.
- Email templates (017). Text email stays text.

## Locators (recon first, then fix these paths in your notes)

- `brand/` — repo root, Dane's files. Read-only source of truth.
- `frontend/scripts/generate_identity.py` — 022's generator (Pillow via
  backend venv, palette from `global.css`, words from `site.config.json`).
  Retire or rewrite as `sync_brand.py`.
- `frontend/public/` — `favicon.ico`, `apple-touch-icon.png`,
  `icon-192.png`, `icon-512.png`, `og.png`, `site.webmanifest`,
  `robots.txt`. Fixed names (022 decision: scrapers fetch blindly).
- `frontend/src/` — `favicon.svg` on the hashed asset pipeline.
- `frontend/index.html` — SITE_ tokens, `og:image`, JSON-LD `logo`.
- `frontend/site.config.json`, `vite.config.js` (`siteMeta` plugin).
- `frontend/src/styles/global.css` (or wherever the palette tokens live).
- `frontend/src/components/SiteHeader/` — 025.
- `frontend/src/components/AdminNav*` — rendered by the twelve `Admin*`
  pages only (025 recon).
- `frontend/src/pages/ComingSoon/` — 015 landing page, served by
  `SiteGate` for every path while `coming_soon`.
- `backend/app/services/certificates.py` — `render(snapshot) -> bytes`,
  vendored DejaVu fonts (011 non-Latin fix).
- `backend/tests/test_identity.py` (022), certificate tests (018/011),
  `SiteHeader.test.jsx` (025), any `AdminNav` test.
- `backend/Dockerfile` (`python:3.12-slim`), `backend/requirements*.txt`.
- `docs/OPERATIONS.md` "Site identity (022)".

## Data model

No migration. No table changes. `sponsor_profile` untouched.

## Tasks

### Task 1 — Inventory `brand/` and write the manifest

List every file in `brand/`. Write `brand/README.md` mapping each file to
a role. Required roles: **primary logo** (horizontal, for header and
certificate top), **mark** (square, for favicon/icons/seal), **palette**
(hex values, either from a file Dane included or sampled from the logo
and confirmed in the README). Optional: wordmark, dark-background
variants, an OG-specific composition. Record the source formats (SVG
preferred; if only raster, note the largest dimension). If a required
role is missing or ambiguous, stop and ask.

Add to `brand/README.md`: "Assets created by Dane for superCPE, LLC.
Owned outright; no third-party license." The Flaticon-derived
`favicon.svg` is deleted in Task 2, and OPERATIONS.md notes the retirement.

### Task 2 — `sync_brand.py` replaces `generate_identity.py`

`frontend/scripts/sync_brand.py` (same runtime as 022: backend venv,
Pillow; add `cairosvg` only if SVG→PNG rasterization needs it and note
the dependency). It reads `brand/` and writes:

- `frontend/public/favicon.ico` (32 + 16), `icon-192.png`, `icon-512.png`
  (maskable-safe padding), `apple-touch-icon.png` (180).
- `frontend/src/favicon.svg` (mark, hashed pipeline as in 022).
- `frontend/public/og.png` 1200×630 — brand composition: mark or logo
  plus the one line from `site.config.json`. No other words.
- `backend/app/assets/brand/` — logo and mark in the formats the
  certificate template needs (SVG if the renderer embeds it; else PNG at
  2× print size). The backend cannot read `frontend/`; this copy is the
  reason the script exists.

Idempotent; a second run produces byte-identical output. `--check` mode
exits non-zero if any output differs from `brand/` (add to the pre-
changelog lint line in CLAUDE.md so a stale asset fails locally).
Delete `generate_identity.py` and its DejaVu/monogram code paths.

### Task 3 — Palette and header

Set `global.css` tokens to the brand palette from Task 1. Check contrast
on every text-on-color pair the site uses (WCAG AA, 4.5:1 body / 3:1
large); if the brand's accent fails on white, keep it for marks and
borders and pick the nearest passing tint for text — record the values.
`theme-color` in `index.html` follows via `siteMeta`.

`SiteHeader`: the text wordmark becomes the primary logo `<img>` with
`alt="superCPE"` (the `site.config.json` name), same link targets, height
capped so the row does not grow. 025's tests still assert: no `<header>`
in coming_soon, no course fact, no Registry string.

### Task 4 — Landing page

Redesign `frontend/src/pages/ComingSoon/` with the assets and palette.
Structure: logo, the one-line tagline, the existing paragraphs, the
waiting-list form, the conditional policies footer, the conditional
Registry block (renders only behind `may_claim_registry`; still false).
Mobile-first; single column under 720px.

Hard rules carried from 015/022, unchanged and still tested:
- No credit figure, field of study, level, prerequisites, price, or any
  8.01 item. Partial disclosure is worse than none (024).
- No `/login` link. No "National Registry" text and no Registry image.
- The `GET /api/v1/landing` payload gains no field.
- No analytics, third-party script, or web font fetched from a CDN. If
  the brand specifies a typeface, vendor it under `frontend/public/fonts/`
  with its license file, or fall back to the system stack.

### Task 5 — Certificate from an HTML template

`backend/app/templates/certificate.html` + `certificate.css`, rendered by
WeasyPrint. Add `weasyprint` to requirements and its system libraries
(pango, cairo, gdk-pixbuf, fonts) to the Dockerfile. If the image build
on `python:3.12-slim` fails or grows past ~150 MB, stop and report the
size before choosing another renderer — do not switch to headless
Chromium on your own.

`render(snapshot) -> bytes` keeps its signature and is still the only
entry point. Template context is the snapshot and nothing else — no DB,
no session, no network. The brand mark loads from
`backend/app/assets/brand/` via a `file://` base URL; WeasyPrint's URL
fetcher is restricted to that directory and the fonts directory (deny
`http`/`https`).

Layout: one page, US Letter, framed in the brand palette. Logo top
center. Participant name and course title as the focal point. Credit
award set off. The Section 9 items as one clean labeled block. Footer
band: certificate number, verification URL, awarding entity
(`sponsor_legal_name`, 9.01.1). Optional mark as a low-opacity seal.

Must survive, pinned by test:
- Every 9.01 item 1–11 prints as **extractable text** exactly as today,
  in the same words: item 5 "Not applicable (self study)"; item 8 only
  when the snapshot carries it; item 10 the 50-minute time statement.
  Existing text-extraction tests pass unchanged or with only whitespace
  adjustments — if a test needs a *wording* change, that is a bug in the
  template.
- Non-Latin participant names render (011). DejaVu stays as the body
  font or as the fallback in the `font-family` stack; a brand display
  font is used for fixed headings only.
- Fonts and images are embedded; the PDF opens offline.
- Output is deterministic for a given snapshot (set WeasyPrint's
  creation date from the snapshot's issued-at, not `now()`), so the
  stored-once invariant is checkable.
- Under 500 KB.

### Task 6 — Admin nav on mobile

`AdminNav`: at and below 720px, the row collapses to the logo/section
title, a menu button (`aria-expanded`, `aria-controls`), and Sign out.
The button opens a vertical list of the same links plus the signed-in
email. Above 720px the current row stays, with `flex-wrap: wrap` so a
new link never pushes Sign out off-screen again. No dependency; CSS +
`useState`. Sign out behavior unchanged (navigates to `/login`, 025).

Check `SiteHeader` at 375 and 720px with a participant signed in (five
items + email). If it overflows, apply the same pattern; if it wraps
acceptably, leave it and say so in the entry.

### Task 7 — Docs

- OPERATIONS.md: replace "Site identity (022)" with "Brand assets (032)":
  where the source lives, how to run `sync_brand.py`, `--check`, why
  favicon and link-preview caches lag a deploy (unchanged from 022),
  the Flaticon retirement, and the certificate renderer's system deps.
- CLAUDE.md pre-changelog line gains `sync_brand.py --check`.
- `docs/decisions/2026-09-13-brand-assets.md`: one source directory,
  copy-by-script, sponsor mark = brand mark, HTML→PDF renderer, no
  Registry mark until approved.
- ROADMAP.md: note the earlier 032 draft superseded; `logo_path` slot
  deferred to a multi-sponsor feature.

## Tests

Backend:
- `test_identity.py`: every 022 assertion still passes against the new
  `index.html` and `og.png` (no "National Registry", no "QAS", no credit
  figure, no price; absolute `og:image`; JSON-LD `logo` resolves to the
  brand file; manifest icons exist at the pinned sizes).
- New: `sync_brand.py --check` passes in CI-equivalent (`pytest` marker
  or a subprocess test).
- Certificate: existing extraction tests pass; new tests assert one page,
  embedded fonts (`pdffonts` or pypdf font-descriptor walk), no external
  resource references, byte-identical output on two renders of one
  snapshot, a non-Latin name round-trips, size < 500 KB, and the string
  "National Registry" is absent when `may_claim_registry` is false in
  the snapshot.
- Landing payload key-set test (015) unchanged and passing.

Frontend:
- `SiteHeader.test.jsx`: existing assertions; wordmark is now an `img`
  with `alt="superCPE"` linking to the same targets.
- `AdminNav.test.jsx`: at a narrow `matchMedia`, the links are hidden
  until the menu button is pressed; pressed → all links and the email
  visible; Sign out present in both states and calls logout once.
- `ComingSoon.test.jsx`: renders the logo; no `/login` link; no Registry
  text with `may_claim_registry: false`; Registry block renders when
  true (existing behavior); waiting-list form still submits.

Lint: pyflakes, oxlint, both suites, `sync_brand.py --check`.

## COMPLIANCE.md rows

- **9.01 / 9.01.1** — update row on the 018 certificate entry: renderer
  changed to an HTML template (WeasyPrint); item content, order, and
  wording unchanged; snapshot-only rendering retained; brand mark added;
  Registry mark still absent. Tests named.
- **8.01** — update row on 015/022: landing page redesigned; no
  descriptive-material item added; payload key-set test unchanged.
- **9.01 item 8 (003 Registry-claim rule)** — new row: no brand asset,
  OG card, or certificate template contains the Registry mark or the
  words "National Registry"; asserted by test on `index.html`, `og.png`
  alt/JSON-LD, and the rendered PDF text.
- **9.02.2** — note only: retained certificate PDFs now carry embedded
  fonts and images (self-contained). No retention rule changes; all
  current production records are test data.

## Acceptance

1. `brand/README.md` maps every file to a role; `sync_brand.py` runs
   twice with identical output; `--check` passes clean and fails after
   touching one output file.
2. Local dev: tab icon, apple-touch (Safari "Add to Home Screen"), and
   `og.png` at `/og.png` show the brand. `index.html` has no Vite default
   and no 022 monogram reference.
3. Header shows the logo image on every open surface; absent in
   coming_soon (025 rule).
4. Landing page at 375px and 1280px: logo, tagline, paragraphs, form,
   conditional footer. Page text contains no credit figure, no price, no
   "National Registry", no `/login`.
5. Issue a test certificate locally: one page, brand logo, every 9.01
   item present in `pdftotext` output, non-Latin test name prints, file
   under 500 KB, opens with network disabled.
6. Admin at 375px: all nine admin links, email, and Sign out reachable
   without horizontal scroll; Sign out works from the open menu.
7. `docker build` of the backend succeeds; image size recorded in the
   entry.
8. **Operator:** deploy, hard-refresh `https://supercpe.com`, confirm
   favicon and `https://supercpe.com/og.png`; paste the URL into a link
   previewer; issue one certificate on production and open the PDF.

## Open questions for Dane (answer in the entry, don't block on 1–2)

1. The landing page's paragraph still describes the ASC 842 course "in
   preparation"; the current course is ATO. Keep, replace with a
   course-neutral sentence, or new copy from Dane? Default if silent:
   course-neutral ("our first courses are in preparation").
2. If the brand specifies a typeface, is it licensed for web embedding
   and PDF embedding? Default if silent: system stack + DejaVu.

## When done

Append the 032 entry to `CHANGELOG.md` once lint, both suites, and
Acceptance 1–7 pass locally. List Acceptance 8 under Known gaps as "not
yet run by the operator" (CLAUDE.md rule 5, relaxed 2026-09-12). Record
the image size, the palette values chosen, and any contrast substitution.
