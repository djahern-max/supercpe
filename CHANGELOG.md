# Changelog
Append-only. Newest at the bottom. Never edit or delete a past entry —
if something was wrong, write a new entry saying so.
---

## 001 — Walking skeleton
Shipped: 2026-08-27

**What changed**
- Repo scaffolding: `CLAUDE.md`, `CHANGELOG.md`, empty `COMPLIANCE.md` matrix,
  `.gitignore`, `docker-compose.yml` (Postgres 16 on 5432, named volume,
  credentials from `.env`), root and per-app `.env.example` files
- `docs/` populated with the four Standards PDFs alongside the existing
  `course-package.md`
- Backend: FastAPI app "superCPE API" with CORS from settings,
  pydantic-settings config (`DATABASE_URL`, comma-separated `CORS_ORIGINS`),
  SQLAlchemy 2.0 engine/session/`Base`/`get_db`, `GET /api/v1/health` running
  `SELECT 1` (200 ok / 503 unavailable), Alembic wired to `app.config.settings`
  and `Base.metadata` with `app.models` imported for future autogenerate
- Frontend: Vite React app stripped of boilerplate, `src/styles/global.css`
  design tokens, `src/api/client.js` + `src/api/health.js`, App renders the
  superCPE wordmark and a green "Backend connected" / red "Backend unreachable"
  status pill
- One backend test: `tests/test_health.py` asserts 200 and status "ok"

**Standards touched**
- None — scaffolding.

**Decisions**
- Vite's current template scaffolds React 19; pinned back to React 18 to match
  the documented stack
- Stopped the machine's Homebrew `postgresql@16` service (user-approved): it
  listened on 127.0.0.1:5432 and shadowed the Docker container's port mapping.
  Restart with `brew services start postgresql@16` if another project needs it
- Health endpoint returns the 503 body via `JSONResponse` so the error shape
  bypasses the 200 `response_model`

**Known gaps**
- `COMPLIANCE.md` is empty by design; rows begin with feature 002

## 002 — Course package ingest
Shipped: 2026-08-27

**What changed**
- Contract edit in `docs/course-package.md`: `learning_objectives` is now an
  array of `{id, text}` objects (ids unique in the manifest, referenced by
  `questions.json` `objective_ids`), and `content_hash` is now defined exactly:
  lowercase hex sha256 over the raw bytes of transcript.md + questions.json +
  video.mp4, concatenated in that order. Still `package_version: 1`; nothing
  had produced a v1 package yet.
- `lesson_packages` table (first Alembic migration, `d770a4d597c5`) holding
  validated scalars plus the manifest, questions, and transcript verbatim.
  CHECK constraints on `duration_source = 'measured'`, field of study, and
  knowledge level; unique on `content_hash` and on `(lesson_id, version)`.
- `POST /api/v1/admin/packages` accepts a zip, runs every contract rule, and
  returns all failures at once as 422 `{"errors": [...]}`. Nothing is written
  unless every rule passes. `GET /packages`, `GET /packages/{id}` (manifest and
  questions, no transcript), `GET /packages/{id}/transcript` (text/markdown).
- Idempotency and versioning: same hash returns 200 with `created: false`;
  same lesson_id with a new hash creates version N+1; a new lesson_id starts
  at version 1.
- ffprobe measures every uploaded video (`app/services/ffprobe.py`); the app
  refuses to boot if ffprobe is missing. Manifest duration must agree with
  ffprobe within 1 second, and `duration_source` must be `"measured"` — the
  refusal message cites 7.02.7.
- `Storage` protocol with a `LocalStorage` implementation rooted at
  `STORAGE_ROOT` (default `backend/uploads/`, gitignored); keys are
  `packages/<lesson_id>/v<version>/video.mp4`.
- `X-Admin-Token` auth via `require_admin` (`secrets.compare_digest`);
  `ADMIN_TOKEN` added to config and `.env.example` files.
- Constants: `app/constants/fields_of_study.py` (20 fields with NASBA's
  technical/non-technical classification, from `docs/2024-Fields-of-Study.pdf`)
  and `app/constants/knowledge_levels.py` (the five levels of 3.01.1, the
  three that require prerequisites under 3.02.1, and the literal "None").
- Frontend: react-router-dom with routes `/`, `/admin/packages`, `*`. Admin
  page with in-memory token form (no localStorage), zip upload, per-line 422
  errors, created/not-created result panels, package table (duration as m:ss),
  row-click detail with formatted manifest/questions JSON and transcript view.
- Tests: `tests/factories/package.py` builds a real tiny package (2-second
  ffmpeg-generated mp4, correct hash by default, overrides to break fields);
  16 tests in `tests/test_packages.py` cover the acceptance list against a
  dedicated `supercpe_test` database. `scripts/make_sample_package.py` writes
  a sample zip to /tmp for manual testing.

**Standards touched**
- 3.01.1 — knowledge level constrained to the five defined levels at
  validation and again by CHECK constraint
- 3.02.1 — prerequisites and advance preparation required for Intermediate/
  Advanced/Update, blank Basic/Overview stored as the literal "None"
- 7.02.7 — duration measured server-side with ffprobe; estimated durations
  refused with a message citing the paragraph
- 9.02.1(8), 9.02.2(7) — program materials (manifest, questions, transcript,
  video) retained verbatim
- COMPLIANCE.md gained its first four rows for these locators.

**Decisions**
- Storage is a three-method protocol (`put`/`open`/`exists`) with local disk
  as the only implementation; DigitalOcean Spaces becomes a second
  implementation at deployment time without touching ingest.
- Raw JSON is stored alongside the validated scalars deliberately: the scalars
  are what this feature validated, the JSON is what later features normalize,
  and history can be re-validated without re-uploads if ingest missed a rule.
- The CHECK constraints are declared on the model (so autogenerate emitted
  them inside `create_table` and tests get them from `create_all`) and
  verified by hand in the migration.
- New dependency: `python-multipart`, required by FastAPI for multipart file
  uploads. No wrapper library for ffprobe; it is one `subprocess.run`.
- Tests run against a `<dbname>_test` database created on demand so they can
  truncate freely without touching dev data.

**Known gaps**
- Shared-token auth is temporary; accounts and roles are feature 009.
- Spaces is not yet implemented; storage is local disk only.
- The video-tool attestation that narration was rendered from measured audio
  is trusted, not verified; superCPE refuses packages that lack it but cannot
  check it (recorded in COMPLIANCE.md under 7.02.7).

## 003 — Sponsor identity record
Shipped: 2026-08-27

**What changed**
- `sponsor_profile` singleton table and `sponsor_state_registrations` table
  (migration `d287428522f0`); the migration itself inserts the id=1 row with
  defaults, so the application never starts without a profile.
- Three CHECK constraints, declared on the model and hand-verified in the
  migration: `id = 1`, `registry_status IN ('not_registered', 'registered')`,
  and `registry_status = 'registered' OR national_registry_id = ''`.
- `app/constants/certificate.py`: `TIME_STATEMENT` (9.01 item 10) and
  `CERTIFICATE_SPONSOR_FIELDS` (the sponsor facts a certificate cannot be
  issued without).
- `missing_fields()` on the model returns the blank certificate-blocking
  fields plus `registry_status` when not registered; `may_claim_registry` is
  the single boolean later features read before rendering the words
  "National Registry" or a sponsor ID.
- `app/services/sponsor.py`: `get_profile`, `update_profile`,
  `set_state_registrations` (full-set atomic replace). Contradictory registry
  states (registered with a blank ID, not_registered with an ID) are refused
  as 422 `{"errors": [...]}` naming the rule before the CHECK fires.
- Routes: `GET`/`PUT /api/v1/admin/sponsor` and
  `PUT /api/v1/admin/sponsor/state-registrations` behind `require_admin`;
  public `GET /api/v1/sponsor` returning only `name`, `website`, and — only
  when `may_claim_registry` — `national_registry_id` (the field is absent,
  not null, otherwise).
- Frontend: `/admin/sponsor` page with the launch-readiness status panel
  ("Certificates can be issued" or the missing items in plain language), the
  profile form, and an editable state-registrations table. Selecting
  `not_registered` clears and disables the ID field; `registered` enables and
  requires it. A small `AdminNav` now links the two admin pages.
- Tests: 12 in `tests/test_sponsor.py` covering the acceptance list; the test
  truncation now covers the sponsor tables too.
- `.env.example` now says the token protects sponsor and package admin.

**Standards touched**
- 9.01 items 1, 8, 9, 10, 11 — the certificate's sponsor facts now have a
  home: profile fields, state registrations as rows, the fixed time
  statement, and free-text other statements
- 9.01.1 — `legal_name` records the entity responsible for awarding the
  credits
- 9.02 — five-year retention added to COMPLIANCE.md as a row whose gap is
  that the period is not yet a constant in code
- COMPLIANCE.md gained three rows for these locators.

**Decisions**
- Singleton by CHECK (`id = 1`), not convention: a second sponsor row is a
  state this application has no meaning for, so the database refuses it
  rather than code politely avoiding it.
- State registrations are rows with a unique state code, not a text blob,
  because certificates will print them and 9.01 item 9 is per-state.
  superCPE does not encode which states require registration; it stores what
  the sponsor actually holds.
- The registry-status rule: NASBA Registry membership is a fact, not a
  setting. Until superCPE is accepted, `national_registry_id` must be empty
  (CHECK plus a named 422) and nothing may claim membership; the claim
  becomes possible only by flipping `registry_status` once it is true.
- `get_profile` re-creates the row if absent even though the migration seeds
  it, because test databases are built by `create_all`, which runs no
  migration inserts.
- Service rule violations raise `SponsorRuleViolation` and the routers wrap
  them in the same 422 `{"errors": [...]}` shape as package ingest, so the
  admin frontend handles both identically.

**Known gaps**
- superCPE is not on the National Registry; `missing_fields` will include
  `registry_status` until it is, and no certificate can be issued.
- The 9.02 five-year retention period is not yet a constant anywhere in
  code; feature 011 adds it.
- The "may not claim Registry" rule is enforced on this feature's own
  responses only. Every later feature that renders sponsor facts (course
  pages, certificates, the audit bundle) must read `may_claim_registry`
  before printing the words "National Registry" or a sponsor ID.
