# Current Feature

## Feature 032 — Certificate redesign: render from an HTML template

> Confirm 032 against the last entry in `CHANGELOG.md` before starting. 031 (player seeking) may or may not have shipped; this feature does not depend on it.

## Goal

The certificate PDF is rendered from an HTML/CSS template instead of drawn by hand, and looks like a certificate: a framed one-page layout in the site's palette, the sponsor mark at the top, the participant's name and the course title as the focal point, the credit award set off, the Section 9 items grouped into a clean block, and a footer band with the certificate number and verification URL.

Nothing about what the certificate says changes. Every 9.01 item, the 9.01.1 awarding entity, the time statement, and the verify line print exactly as today, as extractable text, from the snapshot alone.

## Why

The current `render(snapshot) -> bytes` in `backend/app/services/certificates.py` is a one-page PDF drawn primitive by primitive. It is correct and plain. Certificates are the one artifact a participant keeps and hands to a state board or employer; the sponsor wants them to look considered. Rendering from an HTML template puts layout in CSS where it is cheap to iterate, and lets the mark and palette come from the same sources the site already uses (022's identity script and `global.css`).

Standards this touches, from the 2026 Statement — cite from the PDF, not from memory:

- 9.01 — the eleven certificate items. Nothing added, nothing dropped, nothing reworded. Item 5 still prints "Not applicable (self study)"; item 8 still prints only when the snapshot carries it (`may_claim_registry` at completion).
- 9.01.1 — the awarding entity (`sponsor_legal_name` from the snapshot) stays on the page.
- 9.02 / 9.02.2 — the PDF is a retained record. Already-rendered PDFs are stored once at `certificates/<number>.pdf` and are never re-rendered; the new look applies to certificates rendered after this ships. Pre-launch that is all test data.

## Read first

- `CLAUDE.md`
- `CHANGELOG.md` entries 003 (sponsor profile, `may_claim_registry`), 010 (snapshot, `render`, lazy render), 011 (DejaVu fonts, non-Latin names, audit bundle contents), 019 (delivery, verify line wording), 022 (identity script, palette from `global.css`)
- `COMPLIANCE.md` rows for 9.01, 9.01 items 1/8/9/10/11, 9.01.1, 9.02
- `backend/app/services/certificates.py`, `backend/app/constants/certificate.py`, `backend/tests/test_certificates.py`, `backend/tests/test_audit_bundle.py`
- `frontend/scripts/generate_identity.py` and `frontend/src/global.css` (palette source)
- `deploy/Dockerfile` (base image `python:3.12-slim`; system packages)
- 9.01 and 9.01.1 in the 2026 Statement PDF.

## Task 0 — recon, answered in the changelog before code is written

1. **Current library.** Name the PDF library `render` uses today and every other caller of it in the backend (the audit bundle? anything else?). If nothing else uses it, it is removed with this feature; if something does, it stays and only `render` changes.
2. **What the tests pin.** List each assertion in `test_certificates.py` and `test_audit_bundle.py` that reads the PDF: text extraction of the 9.01 items, the non-Latin name test, the "National Registry" absence test, the verify-line wording, the page count, anything else. Every one must still pass against the new renderer unchanged, or with only the extraction helper swapped.
3. **Palette and mark.** Confirm how `generate_identity.py` reads `global.css` and what it outputs (SVG monogram, PNGs). Name the function or file the backend can reuse for the mark. The backend must not import from `frontend/`; the mark is either copied into `backend/app/assets/` by the identity script or committed there — say which and why.
4. **Renderer choice.** Confirm WeasyPrint installs on `python:3.12-slim` with the system packages it needs (pango, cairo, gdk-pixbuf, fonts) and what that adds to the image size and build time. If it is unreasonable, propose the alternative (headless Chromium via Playwright is the fallback) with its cost. Do not pick a renderer that needs a network call at render time.
5. **Fonts.** Confirm the vendored DejaVu Sans files in `backend/app/assets/fonts/` can be declared via `@font-face` in the template so the non-Latin name test still passes. If a second display face is wanted for headings, it must be vendored with its license the same way DejaVu was in 011, or not used.
6. **Snapshot fields.** List every key in `certificate_snapshot` the current `render` reads, so the template context is exactly that set and nothing from live tables.

## In scope

- New renderer: `render(snapshot) -> bytes` keeps its signature and contract (snapshot only, no session, one page). Internally it fills a Jinja2 template at `backend/app/templates/certificate.html` with the snapshot and renders it to PDF. Jinja2 is already a FastAPI dependency; confirm, else add it.
- The template and a `certificate.css` beside it. Palette values are read from a single Python constant module the identity script also writes (or a committed copy of the same values), so the certificate and the site cannot drift apart silently. Name the mechanism in the changelog.
- Layout, in reading order:
  1. Sponsor mark, top center. Source: `SponsorProfile.logo_path` if set, else the 022 monogram from `backend/app/assets/`. The mark is never rasterized text.
  2. "Certificate of Completion" heading; the sponsor name (9.01 item 1) beneath it.
  3. Participant name (item 2), large — the focal point. Must render non-Latin names.
  4. "has successfully completed" line, then the course title (item 3), then field of study (item 4) and "Self study" (item 6, from `PROGRAM_TYPE`).
  5. Credit award (item 7), set off — e.g. a bordered block: the number, "CPE credit(s)", and the `TIME_STATEMENT` (item 10) directly beneath it.
  6. Completion date (item 11's date component as it prints today), location line (item 5, "Not applicable (self study)").
  7. Sponsor block: awarding entity (9.01.1 `sponsor_legal_name`), NASBA sponsor ID (item 8, only when present in the snapshot), state registration numbers (item 9, only those in the snapshot), other required statements (item 11) as stored.
  8. Footer band: certificate number, and the verify line with the exact wording 019 settled ("Verify this certificate at …"). Keep the URL as text, not only a link.
- A signature line for the awarding entity is in scope only as a labeled rule ("Authorized by <legal_name>"); no signature image, no signer name field — the snapshot has none and the profile gets none here.
- `sponsor_profile.logo_path` — new nullable column (migration), admin-editable on `/admin/sponsor` as an upload to storage under `sponsor/logo.<ext>` (Spaces in prod, local in dev, via the existing storage service). PNG or SVG. When null, the monogram is used. The snapshot does NOT gain the logo: the mark is presentation, not a Section 9 fact, and re-rendering an old certificate is not a thing this system does, so there is nothing to freeze.
- Dockerfile: the system packages the renderer needs. Preflight (014a) must still pass; if the renderer needs a boot-time check the way ffprobe has one, add it to the same health/preflight path and say so.
- Admin: a "Preview certificate" action on `/admin/sponsor` that renders a sample snapshot (fixed fake participant, fake course, today's date, current sponsor facts, `may_claim_registry` respected) and returns the PDF inline. Not stored, not logged as a certificate, no `completions` row. This is how the sponsor iterates on the look and how the NASBA application's sample certificate is produced.
- Tests (see below), `COMPLIANCE.md` row updates, changelog.

## Out of scope

- Any change to the snapshot's contents, `create` in `completions.py`, delivery (019), the verification page, or the audit bundle's file set.
- Re-rendering certificates already stored. No backfill, no "re-render all" admin action.
- The NASBA Registry logo or the words "National Registry" anywhere the snapshot does not already carry them. The existing absence test stays and must pass.
- Multi-page certificates, per-course templates, per-jurisdiction variants, or a template editor.
- A second display font unless recon finds a vendorable one with a compatible license and it adds real value; default is DejaVu Sans only.
- Changing the favicon, og image, or the identity script's output for the site. If the identity script gains a step that copies the monogram into `backend/app/assets/`, that is the only change to it.
- Signature images, signer names, or a "signed by" profile field.

## Locators

- `backend/app/services/certificates.py` — `render`
- `backend/app/constants/certificate.py` — `TIME_STATEMENT`, `PROGRAM_TYPE`
- `backend/app/models/sponsor.py`, `backend/app/routers/admin_sponsor.py`, the admin sponsor page in `frontend/src/`
- `backend/app/assets/fonts/`, new `backend/app/assets/brand/` (monogram, palette)
- `backend/app/templates/` (new)
- `backend/tests/test_certificates.py`, `test_audit_bundle.py`, `test_sponsor.py`
- `deploy/Dockerfile`, `backend/requirements*.txt`
- `frontend/scripts/generate_identity.py`, `frontend/src/global.css`
- `COMPLIANCE.md`, `CHANGELOG.md`, `docs/OPERATIONS.md`

## Data model

- `sponsor_profile.logo_path` — nullable text, storage key. One Alembic migration, forward only.
- No change to `completions.certificate_snapshot`.

## Tasks

1. Task 0 recon; write the answers into the changelog draft.
2. Renderer dependency and Dockerfile packages; a unit test that renders a minimal HTML string to a one-page PDF proves the toolchain works in CI and in the image.
3. Palette and monogram into `backend/app/assets/brand/`, with the mechanism that keeps them in sync with the frontend named and tested (a test that the committed palette matches `global.css`, or that the identity script writes both).
4. Template and CSS; `render` rebuilt on it. Every existing certificate test passes.
5. `logo_path`: migration, model, admin route (upload/clear), admin UI, `render` fallback to the monogram.
6. Admin preview route and button.
7. Visual check: render the sample certificate locally, open it, and commit a PNG of it under `docs/` so the changelog can point at what shipped. (Rasterize with the pdf tooling already in the venv or `pdftoppm` if present; do not add a dependency for this.)
8. `COMPLIANCE.md`, changelog, OPERATIONS.md note on the new system packages.
9. pyflakes, oxlint, both suites.

## Tests

Backend:
- All existing `test_certificates.py` assertions pass unchanged (9.01 items extractable, non-Latin name, "National Registry" absent when `may_claim_registry` was false, verify-line wording, one page).
- With item 8 present in the snapshot, the sponsor ID prints; with it absent, neither the ID nor the words appear.
- State registrations in the snapshot print; an empty list prints nothing for item 9.
- `render` with a snapshot only (no session, no profile row) succeeds — pins the snapshot-only contract.
- `logo_path` set → the PDF embeds an image from that key; unset → the monogram is embedded. (Assert on the PDF's image XObjects or on a rendered-pixel hash; either is fine.)
- Preview route: admin-only; returns `application/pdf`; creates no `completions` row and no storage object; respects `may_claim_registry`.
- Audit bundle tests unchanged.

Frontend:
- Admin sponsor page: logo upload, clear, and Preview certificate button call the right routes.

## COMPLIANCE.md rows

Edit Notes on existing rows, no new rows:

| Para | Change |
|---|---|
| 9.01 items 1, 8, 9, 10, 11 | `render` now fills an HTML template (`backend/app/templates/certificate.html`) from the snapshot; the item set and gating are unchanged (032). |
| 9.01.1 | Awarding entity printed as the "Authorized by" line (032). |
| 9.02 | Add: rendered PDFs are never re-rendered; certificates issued before 032 keep the earlier layout. Sponsor logo is presentation and is not part of the snapshot. |

## Acceptance

Locally runnable:
1. Both suites green; lint shows only warnings recorded in earlier entries.
2. `docker build` of the api image succeeds and `preflight` passes inside it.
3. Preview certificate from `/admin/sponsor` opens a one-page PDF with the monogram; upload a logo, preview again, the logo appears; clear it, the monogram returns.
4. Complete the ATO course locally as a test participant; the emailed and downloaded PDFs match the preview layout and the 9.01 text extracts.

Operator, under Known gaps as "not yet run by the operator":
5. Deploy; preview on production; complete a course on production and check the emailed certificate arrives through Resend with the new PDF attached.

## When done

Append the 032 changelog entry with Task 0 answers, the renderer chosen and why, the palette-sync mechanism, the path to the committed sample PNG, verification table, Known gaps, and Decisions (HTML-template rendering; logo as presentation not snapshot; no re-render of stored PDFs). Report, do not build, anything out of scope.
