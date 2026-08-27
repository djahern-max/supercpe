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

## 004 — Courses assembled from lesson packages
Shipped: 2026-08-27

**What changed**
- Contract edit in `docs/course-package.md`: `course_code` (groups lessons
  into a course) and `position` (the lesson's order within it, a positive
  integer) are now required manifest fields. Still `package_version: 1`.
  current-feature.md said the one pre-existing package was `HAZWASTE-01`; it
  was actually `ASC606-CON-01` v1 (the 002 fixture). Either way it predated
  the rule, carried no `course_code`, was refused on attach for exactly that
  reason, and was deleted during acceptance.
- Ingest rule: a manifest without `course_code` or `position` is refused;
  `position` must be >= 1. The values live in the stored manifest, exposed as
  model properties, not as new `lesson_packages` columns.
- `courses` and `course_lessons` tables (migration `d014c39c688d`). CHECKs:
  `status IN ('draft', 'published')`, `position >= 1`; unique on
  `(course_id, position)` and `(course_id, package_id)`; FK cascade from
  course to its lessons, FK restrict from lessons to packages.
- `app/services/courses.py`: create/update/delete course, attach (checks in
  order: not already attached anywhere, no other version of the same
  `lesson_id`, agreement on the four derived fields or first lesson sets
  them, manifest `course_code` equals the course's, manifest position free),
  detach (clears derived fields when the last lesson goes), move up/down
  with a two-pass renumber that parks positions above the occupied range and
  then assigns a dense 1..n, update-version (same lesson, strictly newer,
  same derived fields), `course_objectives` (grouped by lesson in position
  order, keyed for 006 by `(package_id, objective_id)`), and `touch` — the
  single choke point that bumps `content_updated_at` on every mutation a
  participant could observe. Violations raise `CourseRuleViolation`,
  translated to the same 422 `{"errors": [...]}` shape as 002 and 003.
- `app/services/packages.py`: `delete_package` (refused while attached,
  removes the storage object; `Storage` protocol gained `delete`) and
  `list_packages` now annotates each package with `attached_to`.
- Routes: admin CRUD under `/api/v1/admin/courses` plus attach, detach,
  move, update-version, and `DELETE /api/v1/admin/packages/{id}`. Public
  `GET /api/v1/courses` and `GET /api/v1/courses/{course_code}` serve
  published courses only with the full 8.01 disclosure payload — so they
  correctly serve nothing until 008 publishes something.
- Frontend: `/admin/courses` (list, create form), `/admin/courses/:code`
  (inline title/description edit, read-only derived facts with a note that
  they come from the lessons, lesson table with move/detach/"Update to vN",
  attach panel filtered to unattached packages whose `course_code` matches,
  per-line 422 errors), `/admin/packages` gained an "Attached to" column and
  a confirm-guarded delete on unattached rows, and the first
  participant-facing surfaces: `/courses` (catalog; the empty state is a
  plain sentence) and `/courses/:code` (single-column disclosure page in
  reading order: title, description, objectives by lesson, level,
  prerequisites, advance preparation, field of study, lessons with
  durations).
- Tests: 12 in `tests/test_courses.py` covering the acceptance list; the
  package factory gained `course_code`/`position` defaults and an `OMIT`
  sentinel for removing manifest keys. 41 tests total.

**Standards touched**
- 3.01 — course objectives are derived from the lesson packages and shown
  grouped per lesson, in the admin and in the public payload
- 3.01.1, 3.02.1 — level, prerequisites, and advance preparation are
  course-level facts enforced to agree across every attached lesson; the
  admin cannot type values that contradict the content
- 7.01.1 — deliberately not implemented: a course requires a single field of
  study *because* 004 chose refusal over the paragraph's multi-field credit
  allocation; recorded as a Gap
- 8.01, 8.01.1, 8.01.2 — the public course payload and page carry the
  disclosure elements this phase can know (objectives, description, level,
  prerequisites, advance preparation, field of study, lessons with
  durations); credit arrives with 005, policies with 011
- COMPLIANCE.md gained rows for 3.01, 3.02.1 (course-level), 7.01.1, 8.01/
  8.01.1, and 8.01.2, and the two 002 rows' gaps now point at the publish
  gate instead of "no surface exists".

**Decisions**
- Course facts are derived from packages, not typed: the admin types only
  `title` and `description`; everything else is copied from the packages and
  disagreement is refused with a message naming the field and both values.
  This is the deliberate departure from abacadaba, which validated typed
  values instead of eliminating them.
- One field of study per course. Attaching a lesson from another field is
  refused rather than allocating credit per 7.01.1's second paragraph.
- `touch(course)` in the service is the only writer of
  `content_updated_at`; every later staleness computation (credit, review)
  reads that single column.
- `course_code` and `position` stay in the stored manifest (exposed as model
  properties) rather than becoming `lesson_packages` columns, since the
  pre-rule package legitimately has neither and the manifest is already
  stored verbatim.
- Reorder renumbers positions densely (1..n), so a sparse manifest position
  (say 5 of 3) survives attach but not the first reorder.
- Detaching the last lesson clears the four derived fields back to null;
  an empty course claims nothing about content it no longer has.

**Known gaps**
- No publish: `status` only ever holds `'draft'` through the app; the
  public routes were exercised by flipping the row in psql and flipping it
  back. 008 owns the real gate.
- No multi-field allocation (7.01.1); refusal is the whole implementation.
- Objectives are not editable in superCPE, only in the package via
  video-tool re-export.
- The public payload has no recommended CPE credit (005), no type of formal
  learning program, and no registration/refund/complaint policies (011).
- Deleting a package removes the storage object but leaves its empty
  `packages/<lesson_id>/v<N>/` directory behind.

## 005 — Credit measurement
Shipped: 2026-08-27

**What changed**
- `courses` gained the eight credit columns (`credit_award` numeric(4,1),
  `credit_raw_minutes` numeric(8,2), the three input totals,
  `credit_breakdown` JSONB, `credit_formula_version`,
  `credit_computed_at`), migration `df4aae4f2bba`. Staleness is derived
  (`credit_computed_at` vs `content_updated_at`, formula version vs the
  constant), never stored.
- `app/constants/credit.py`: every number NASBA chose (50, 180, 1.85, 0.2,
  the formula version, the 8.01 basis string).
- `app/services/credit.py`: `compute` runs the 7.02.6 word count formula
  over the attached packages — per lesson, `av_is_additional_learning`
  selects the measured duration or the manifest word count (7.02.7), and
  every stored question of both kinds counts; `round_down` floors to
  one-fifth and returns 0.0 below the minimum awardable; `store` writes the
  result without touching `content_updated_at`; `is_stale`/`stale_reason`
  derive freshness; `from_stored` + `as_text` rebuild the written-out
  calculation from the stored columns alone (the 9.02.2(2)(ii) record).
- Every `courses` service mutation that goes through `touch` (create,
  update, attach, detach, move, update-version) ends in `store`, plus an
  explicit `POST /admin/courses/{code}/credit/recompute` for the stale
  cases mutations cannot reach.
- Admin: `/admin/courses/:code` gained a Credit panel between the derived
  facts and the lesson table (award large, the three terms, sum, ÷ 50, raw,
  rounded, per-lesson rows, a "Show calculation" toggle over `as_text`, an
  amber stale line with Recompute); `/admin/courses` gained a credit column
  with a stale marker.
- Public: `GET /courses` and `GET /courses/{code}` gained
  `recommended_credit` and `credit_basis`, null while stale or below the
  minimum awardable; the `/courses/:code` page shows the credit with the
  basis beneath it and omits the row entirely when null.
- Tests: 11 in `tests/test_credit.py`, `Decimal` assertions throughout,
  with the abacadaba golden case (486 s all-video, 8 questions → raw
  0.458, award 0.4). 52 tests total.

**Standards touched**
- 7.01 — awards floor to one-fifth increments uniformly, never up, with a
  minimum awardable of 0.2
- 7.02 — method 2 chosen; method 1 deliberately absent (Gap)
- 7.02.5 — only the manifest's `word_count` enters the word term; the
  transcript is never counted and questions are counted separately (Gap:
  the number is trusted from video-tool)
- 7.02.6 — the formula, computed at course level from stored inputs, with
  review and assessment questions both counted
- 7.02.7 — per-lesson branch between measured A/V duration and word count;
  the all-video form falls out as a zero word term
- 8.01 — the recommended credit and its basis are now in the public
  disclosure payload
- 9.02.2(2)(ii) — the per-lesson breakdown and the written-out calculation
  are stored and reproducible from the columns alone; export arrives in 011
- COMPLIANCE.md gained rows for 7.01, 7.02, 7.02.5, 7.02.6, 7.02.7, and
  9.02.2(2)(ii), and the 8.01 row now records the credit disclosure. The
  7.01.1 row's Gap is unchanged.

**Decisions**
- One-fifth rounding uniformly: it is the finest increment 7.01 permits for
  self study and never overstates under any coarser board policy; the
  per-jurisdiction increment policy is roadmap 019 (comment at
  `round_down`).
- Auto-recompute at the end of every mutation that goes through `touch`, so
  an admin never sees a stale credit on a course they just edited;
  staleness exists for formula-version changes and defense in depth, not as
  a normal state. `store` never calls `touch`: computing credit is not a
  content change.
- The per-lesson breakdown is stored (JSONB) rather than recomputed for the
  record, so the 9.02.2(2)(ii) documentation stands even after lessons
  change or detach; `as_text` renders from it alone.
- Formula terms are truncated at two decimal places of a minute
  (ROUND_DOWN), so the retained record re-adds exactly as written and a
  term can only ever understate, never push a credit over a rounding
  boundary.
- The public payload serves null — and the page omits the row — when the
  credit is stale *or* the award is below the minimum awardable: a
  participant is never shown a stale number or "0.0".

**Known gaps**
- Method 1 (7.02.1–7.02.4) is absent by design; superCPE does not pilot
  test.
- `word_count` and `av_is_additional_learning` are trusted from the
  video-tool manifest; superCPE cannot verify either against the content.
- No per-jurisdiction rounding policy (roadmap 019).
- The 9.02.2(2)(ii) record is stored but not yet exportable; the audit
  bundle is feature 011.
- Publish (008) will call `is_stale` and refuse; this feature only exposes
  it.
