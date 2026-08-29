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

## 006 — Questions, and the player with review questions inside it
Shipped: 2026-08-27

**What changed**
- Contract sync: `docs/course-package.md` copied from video-tool 03 so the
  two are byte-identical again; it now carries `manifest.video.blocks`
  (measured start/end seconds per narrated block). Enforced as rule 18 in
  `backend/app/services/packages.py` — one entry per block, ids matching the
  transcript's `## <block id>` headings, contiguous, last end within 1 s of
  `duration_seconds` — and rule 15's `after_block` bound is now
  `[1, len(blocks)]`, replacing the old `narration_blocks` bound. `blocks`
  is a required video field; stored packages without it predate the rule and
  are fixtures.
- `questions` and `choices` tables (migration `cf396feae240`), normalized
  from each package's questions.json per package version: question_key,
  kind (CHECK review/assessment), after_block (CHECK: set iff review),
  position, stem, feedback, objective_keys; choices with exactly one
  `is_correct` per question (enforced by the normalizer and by test).
  `packages.ingest` writes the rows in the same transaction as the package
  row; the migration backfills existing packages (chosen over a script so
  every environment backfills on upgrade). A course's review questions are
  those of its attached packages' current versions.
- `app/constants/question_minimums.py`: `REVIEW_PER_CREDIT`, the 5.01.2.1
  chart, `COUNTING_MIN_CHOICES` (two-choice questions do not count), and
  `required_review_questions` — the above-one-credit decomposition
  (`whole × 3 + chart[remainder]`) is documented in its docstring as an
  interpretation. Room left for 007's assessment constants.
- `app/services/readiness.py`: `check(db, course)` reports findings —
  `credit_missing` (block), `review_minimum` (block, both numbers and the
  credit), `review_placement` (warn: lessons with no review question),
  `review_two_choice` (warn) — plus `review_counts` so the count vs
  requirement shows even when satisfied. Nothing here refuses anything;
  008 turns block findings into a publish refusal.
- Player endpoints behind the admin token (010 moves them behind
  enrollment): `GET /api/v1/courses/{code}/lessons/{package_id}/play`
  (video URL, blocks, review questions with stems and choices — no answer
  key, no feedback) and stateless server-side grading at
  `POST …/review/{question_key}` returning verdict, feedback, and the
  correct choice key (5.01.2.2). `Storage` gained `url(key)`;
  `LocalStorage` serves through the new unauthenticated `/api/v1/media/`
  route (the local stand-in for a presigned Spaces URL — a video element
  cannot send the token header), honoring Range requests.
- `src/components/Player/`: one column, video at reading width, slim
  progress bar with a visible tick at each review point, custom minimal
  controls (play/pause, time, mute) on a native `<video>`. At a review
  point the video pauses and the question appears in place over the video
  area: stem, tappable choice rows, Submit; then the verdict ("Correct" /
  "Not quite"), the feedback, Continue, and on a wrong answer a "Re-watch
  this section" link that seeks to the block's start and resumes. Answering
  is required to continue; any answer continues. Forward seeks past the
  furthest point watched are undone once the seek settles; seeking back and
  re-answering is free. Space toggles play, arrows seek within the watched
  range, choices are focusable, Enter submits. No confetti, no score.
- `/admin/courses/:code/preview` (and `…/preview/:packageId`) lists the
  course's lessons and mounts the player under a "Preview — nothing is
  recorded." banner. `/admin/courses/:code` gained a Readiness card (count
  vs required line, findings as plain block/warn lines) and a Questions
  section (per lesson: review questions with after_block and a
  does-not-count badge on two-choice ones; assessment questions listed
  separately, read-only for 007).
- Tests: 32 new across `test_questions.py` (normalization counts,
  per-version questions, blocks rules, the minimums chart),
  `test_readiness.py`, and `test_player.py` (grading both verdicts, and
  walks of the play and admin payloads asserting the answer key is absent
  — plus the same check against the real preview's network responses in a
  scripted browser). 84 total.

**Standards touched**
- 5.01.2 — the first participant engagement surface: review questions
  asked inside the video, not on a quiz page after it
- 5.01.2.1 — placement at measured block ends ("throughout the program");
  the chart and per-credit minimums as constants; two-choice exclusion; no
  passing rate anywhere
- 5.01.2.2 — verdict and feedback on every answer, server-graded
- 6.01.2 — read, not implemented: its sub-ii feedback rules are why
  nothing here (grading, feedback flow) may be reused for the assessment
- COMPLIANCE.md gained rows for 5.01.2, 5.01.2.1, and 5.01.2.2.

**Decisions**
- Questions belong to a package version, not a course: a version-2 ingest
  writes its own rows and version 1's remain, so a certificate snapshot
  (010) can always point at exactly what was asked.
- In-video placement via `after_block` against measured `video.blocks` is
  how "throughout the program in sufficient intervals" is satisfied;
  the placement warning stays simple (a lesson with zero review questions).
- Forward-seek prevention is a sponsor design choice, not a Standards
  requirement (5.01.2.1 sets no such rule), and is enforced only in the
  player.
- No player library: native `<video>` with custom minimal controls; the
  in-flight-seek clamp lives on `seeked` because re-targeting a seek from
  the `seeking` event can wedge the media element.
- The `/media/` route is unauthenticated by design, mirroring the presigned
  URLs that replace it in 012; video URLs are only handed out by the
  token-gated play endpoint.

**Known gaps**
- Nothing is persisted: review answers and watch progress are lost on
  reload; 010 keys them to the enrollment.
- The qualified assessment is not built; its questions are stored and
  listed read-only, and 007 owns everything else about them.
- "Other content reinforcement tools" (simulations, exercises) are not
  modeled; only multiple-choice review questions satisfy the 5.01.2.1
  floor.
- The readiness checklist only reports; the publish refusal is 008.

## 007 — The qualified assessment
Shipped: 2026-08-27

**What changed**
- 6.01.2 constants: `PASSING_PCT` (70), `OBJECTIVE_COVERAGE_PCT` (75), and
  `RETAKES_ALLOWED` in `app/constants/assessment.py`;
  `ASSESSMENT_PER_CREDIT` (5), the one-fifth chart, the forced-choice floor
  `MIN_CHOICES_ASSESSMENT` (3), and `required_assessment_questions` in
  `question_minimums.py`, reproducing the paragraph's own worked examples
  (5 credits → 25, 5½ → 29). Ingest's pre-existing three-choice refusal now
  aliases the same constant.
- Four block readiness findings: `assessment_minimum` (count vs required,
  both numbers shown), `assessment_forced_choice` (defense in depth behind
  ingest), `assessment_duplicate` (normalized stems — lowercase, collapsed
  whitespace, trailing punctuation stripped — naming both question keys and
  lessons), `objective_coverage` (covered/total keyed by (package_id,
  objective id), uncovered listed by lesson).
- `attempts` and `attempt_answers` tables with migration: preview flag,
  status CHECK (open/passed/failed), snapshot of the passing threshold,
  `package_versions` recorded at start so the attempt proves what was
  asked after any re-export, a partial unique index allowing one open
  attempt per (course, preview identity), and `answer.question_id` with no
  ON DELETE so an asked package version cannot be deleted from under the
  record. `enrollment_id` is a bare nullable column until 010 adds the FK.
- The engine (`app/services/assessment.py`): `start` refuses on stale
  credit or any block finding; `submit` grades the whole form at once,
  requiring every question answered, comparing the exact ratio (correct ×
  100 ≥ 70 × total) so display rounding can never lift a score over the
  floor; `abandon` retains a walked-away attempt as failed with no score;
  `result` is the single source of everything a participant may see.
- Endpoints under the admin token (010 re-gates): GET the assessment
  (questions and choices, never answers or feedback), start, save partial
  answers (refresh-safe), submit, get result — plus
  `GET /api/v1/admin/courses/{code}/attempts` with per-answer detail, since
  the admin may see what the participant may not. Preview identity is an
  opaque per-session `X-Preview-Id` header. Result payloads are plain
  dicts, deliberately un-modeled: a failed attempt's payload simply has no
  per-question keys at all.
- UI: `src/components/Assessment/` — plain intro (count, the 70 percent
  requirement, results-after-submission, retakes), all questions on one
  scrolling page as radio-group rows with no verdicts or colors anywhere
  while open, answers saved on change, a sticky "N of M answered" footer,
  one confirm on submit. Passed: score, then each question with the chosen
  answer, the correct one marked, and the feedback. Failed: score, "70
  percent is required," correct count, Try again — nothing else. Mounted
  at `/admin/courses/:code/preview/assessment`; the course page gained an
  Attempts card (count, pass rate, latest) linking to
  `/admin/courses/:code/attempts` (table, click for every answer).
- Tests: 19 new in `test_assessment.py`. The load-bearing ones walk the
  payloads: a failed attempt's result (and its GET) contains no
  `is_correct`, no correct choice, no feedback, and no per-question array;
  a passed one contains all of them; the open-attempt questions payload
  contains no answers or feedback. Verified end-to-end against ASC842-PCX:
  one wrong of three → 66.67, failed, payload clean; retake all correct →
  passed with feedback. 103 total.

**Standards touched**
- 6.01 — completion verification exists: server-graded, stored attempts;
  nothing self-certified
- 6.01.2 — the 70 percent floor, the per-credit minimums and chart with
  the paragraph's worked examples as tests, the duplicate rule, the
  forced-choice prohibition, 75 percent objective coverage, and sub-ii's
  no-feedback-on-failure rule enforced in `result()`
- 9.02.2(1) — attempts retained in full with the package-version snapshot;
  not yet tied to a participant
- COMPLIANCE.md gained rows for 6.01, 6.01.1 (deliberate n/a), six aspects
  of 6.01.2, and 9.02.2(1).

**Decisions**
- Form-not-sequence because of sub-ii: pass or fail is only known after
  the whole assessment is scored, so no per-question verdict may exist
  while an attempt is open, and none may ever exist for a failed one. The
  failed result stops at score and correct count — the outer limit of what
  a score already reveals.
- No shuffling: question order is package position then question position,
  choices as stored. Auditability of "what was asked" beats the marginal
  integrity gain; a shuffle can be added later with the order stored per
  attempt.
- Retakes allowed as sponsor policy (6.01.2 leaves it to the sponsor's
  discretion); every attempt is retained regardless.
- The passing threshold is snapshotted per attempt, and pass/fail compares
  the exact ratio, never the two-decimal display score.
- Result payloads bypass response models on purpose: an optional-field
  schema could serialize forbidden key names into a failed payload.

**Known gaps**
- No test bank, and therefore sub-ii-a (the other feedback branch) is
  deliberately unimplemented: every question is served every time.
- The recall-as-learning-strategy exemption from the duplicate rule is not
  modeled.
- Attempts are not yet tied to an enrollment; the preview identity is a
  per-session opaque header until 010.
- The retake policy is not yet disclosed on the course page (011).
- Nano learning's 100 percent rule and adaptive learning's path minimum
  are out of scope with their delivery methods.

## 008 — Development and review chain, and the publish gate
Shipped: 2026-08-27

**What changed**
- `subject_matter_experts`: a person qualified on a date — name, free-text
  credentials, a typed `credential_type` (cpa / tax_attorney /
  enrolled_agent / other), license jurisdiction/number/status, all recorded
  as stated and never verified. Deliberately no FK to any accounts table.
  Deletion is refused (DB RESTRICT plus a service check naming the
  courses) while the SME is a developer of record or a named reviewer,
  because 9.02.2(4) retains those names with the record. Admin CRUD at
  `/api/v1/admin/smes` and a new `/admin/smes` page.
- On `courses`: `developer_id`, `developer_used_technology` (default true —
  the 4.01.1 fact about how superCPE content is made), `review_cycle`
  (annual/biennial, CHECK added by hand), `published_at`, `unpublished_at`.
- `course_reviews`: reviewer, review date, decision (approved /
  changes_requested), notes, 4.02.1's `impractical_basis`, `recorded_by`,
  and `content_updated_at_reviewed` — the course's content timestamp at
  recording, so the review is of *that* content. Immutable: no update or
  delete path exists; corrections are new reviews.
- Derived, never stored (`app/services/development.py`): `current_review`
  (latest approved review whose snapshot is >= the course's
  `content_updated_at`), `review_due_at` (reviewed_at + 365/730 days from
  `app/constants/review_cycle.py`), `last_documented_date` (greater of
  `published_at` and the latest review date — the 4.01 disclosure).
- Readiness gained `developer_missing`, `review_missing` (message says
  whether none exists or the content changed since, with both timestamps),
  `reviewer_is_developer`, `cpa_participation` (fields and qualifying
  credentials in `app/constants/participation.py`; either developer or
  reviewer satisfies it, license must be active), `description_missing`
  (all block), and `review_due` (warn).
- The publish gate: `POST …/publish` runs the checklist and refuses with
  every block finding at once as a 422 `{"errors": [...]}`; on success sets
  status published and `published_at`. `POST …/unpublish` sets draft and
  `unpublished_at`. Neither touches content, so the review stays current
  across the round trip.
- Immutability: every course mutation that calls `touch` (title and
  description edits, attach, detach, move, update-version) refuses on a
  published course, naming 4.02 and saying to unpublish first. Setting the
  developer, the cycle, or recording a review is not a content change and
  stays allowed on a published course; a new review advances the
  disclosure date without unpublishing (tested).
- Public payload gains `developed_by` and `reviewed_by` (name and
  credentials only — license numbers proven absent by test),
  `last_reviewed`, `last_documented_date`; the course page shows a
  provenance line after the lessons. Admin course page gained a
  Development & Review card (developer select with the 4.01.1 sentence,
  cycle, review history with current/superseded standing, a record-review
  form with the impractical basis collapsed under a link, and the
  Publish/Unpublish button with the readiness state beside it); content
  controls disable with an immutability note while published.
- Tests: 12 new in `test_development.py`, including the full
  publish → refuse-edit → unpublish → edit → stale-refusal → re-review →
  republish loop. 115 total. Verified end to end against ASC842-PCX, which
  is now published with provenance.

**Standards touched**
- 4.01 — cycle stored, due date and last-documented date derived and
  disclosed; overdue is a warning, enforcement is reporting only
- 4.01.1 — developer of record with the technology flag; gates publish
- 4.02 — distinct reviewer, CPA/EA participation by field, review before
  publish and after revision enforced by immutability plus the
  stale-review block
- 4.02.1 — impractical basis documented as a field, reported, never a
  bypass
- 9.02.2(4) — names, credentials, and license details retained;
  undeletable while referenced
- COMPLIANCE.md gained rows for all five.

**Decisions**
- SMEs are not accounts: a person who was qualified on a date outlives any
  login 009 may add, so there is no FK between the two, ever.
- Published courses are immutable; the only path to changed content is
  unpublish → edit → re-review → republish, which is exactly 4.02's
  review-after-revision rule expressed as state.
- "Significant revision" is read as any content change: every `touch`
  supersedes the current review, because the software cannot judge
  significance.
- The reviewer must differ from the developer (4.02 is explicit); recording
  such a review is allowed, publishing with it is not.
- Sponsor `missing_fields` does not gate publish — publish makes a course
  visible; the registry status gates certificates (010).
- The 008 findings live in `readiness.PUBLISH_ONLY_CODES` and do not block
  `assessment.start`: a draft course's assessment preview is well-formed
  under 6.01.2 before any developer or review exists. The pre-008
  "no findings" assertion in `test_readiness.py` now filters these codes.
- The governmental Accounting/Auditing fields count as accounting and
  auditing for 4.02 participation; the paragraph speaks of the subject,
  not the NASBA catalog line.
- `recorded_by` is the literal "admin": a shared token is the only admin
  identity that exists today.

**Known gaps**
- License and credential claims are recorded as stated, never verified
  against a state board (said in the UI).
- Overdue reviews are reported (warn finding; 011 reports), not enforced,
  and nothing reminds anyone.
- No reviewer login; reviews are entered by the admin on the reviewer's
  behalf until 009 decides otherwise.
- The international-taxes CPA-equivalence allowance of 4.02 is not
  modeled.
- Deleting a draft course cascades its reviews away; retention of reviews
  on delivered courses is protected only by delete being draft-only (010
  revisits deletion).

## 009 — Accounts, roles, sessions, and site mode
Shipped: 2026-08-29

**What changed**
- `accounts` (email, argon2id hash, role, active flag, forced first-login
  password change, login-attempt counter with lockout) and `sessions`
  (sha256 token hash, idle and absolute expiry, revocation) tables, one
  migration; `site_mode` on `sponsor_profile` with an append-only
  `site_mode_changes` log; `recorded_by_account_id` on `course_reviews`.
- `app/services/auth.py` (authenticate, sessions, password change, role
  and activation management) and `app/services/site.py` (mode read/write
  with the log row in the same transaction). Constants in
  `app/constants/auth.py` — none of them NASBA numbers, and the docstring
  says so.
- `require_role(*roles)` in `app/auth.py` replaced `require_admin`
  everywhere; `ADMIN_TOKEN` removed from config, `.env.example` (both),
  and the local `.env`. Every `/api/v1/admin/*` route takes
  `require_role("admin")`; the player and assessment preview take
  `require_role("admin", "reviewer")`. Auth failures are 401 with one
  fixed message, authorization failures 403, and the closed site answers
  404 (`require_site_open_or_session` on `GET /courses`,
  `GET /courses/{code}`, `GET /sponsor`) so it does not advertise what is
  behind it. `/api/v1/health`, `/api/v1/site`, and `/api/v1/auth/*` are
  never gated.
- Routes: `/api/v1/auth` (login, logout, logout-all, me,
  change-password), `/api/v1/admin/accounts` (list, create with a
  one-time initial password, role, deactivate/reactivate,
  revoke-sessions), `/api/v1/admin/site-mode` (+ `/changes`),
  `GET /api/v1/site` (public: mode and sponsor name only), and the
  reviewer surface `/api/v1/review/courses` (list with current-review
  standing), `/api/v1/review/courses/{code}` (read-only facts, history,
  and the SME names the form needs), and
  `POST /api/v1/review/courses/{code}/reviews`.
- `development.record_review` now requires the recording account:
  `recorded_by` snapshots the account's email, `recorded_by_account_id`
  the account. The 008 literal `"admin"` rows are untouched history.
- `python -m app.cli create-admin --email …` creates the first admin,
  prompting for the password (no flag; it would land in shell history);
  refuses if an admin exists unless `--force`.
- Frontend: session context from `GET /me`, `RequireRole` route wrapper,
  `/login` (unlinked), `/change-password`, `/admin/accounts`, a Site mode
  card with confirm step and change log on `/admin/sponsor`, `/review`
  and `/review/courses/:code` for reviewers, and the coming-soon
  placeholder on public pages. The four admin token forms are deleted
  (AdminPackages and AdminSponsor inline, the shared `admin/TokenForm.jsx`
  and `admin/token.js`); `api/client.js` sends `credentials: 'include'`
  and no header. The preview pages now serve reviewers too, reading the
  lesson list from the review endpoint.
- `X-Preview-Id` is unchanged from 007; 010 replaces it with the
  enrollment.
- Tests: 22 new in `test_auth.py` and `test_site.py`, including a walk of
  the router table so a new `/admin` route cannot ship unguarded. 137
  total (was 115), with prior fixtures switched from the token header to
  a logged-in admin client.

**Standards touched**
- 4.02 — reviewers enter their review in the first person; who recorded
  it is stored beside it
- 4.02.1 — unchanged: the SME record stays the qualification, the
  account is only the login (compliance row unchanged)
- 6.01 — the server-vouched participant identity 010's completion
  verification will hang on; new compliance row
- 9.02 — accounts are deactivated, never deleted; sessions and reviews
  FK RESTRICT to accounts
- 9.02.2(1) — unchanged: completion records still wait on 010
  (compliance row unchanged)
- 9.02.2(4) — the account that recorded each review is retained beside
  the reviewer's name and credentials
- COMPLIANCE.md: 4.02, 9.02, and 9.02.2(4) rows appended; a 6.01 row
  added.

**Decisions**
- `argon2-cffi` is the one new dependency: a single maintained library
  for the one hashing primitive needed (argon2id); `passlib` is
  unmaintained. No JWT library — sessions are rows, revocable by UPDATE.
- CSRF posture: the session cookie is `HttpOnly`, `SameSite=Lax`,
  `Secure` outside dev; CORS is same-origin; mutating auth routes
  require `Content-Type: application/json`, which a cross-site form
  cannot send. No CSRF token on top of that.
- No SME↔account FK, ever (restating 008): a person who was qualified on
  a date outlives any login. The reviewer surface names an SME id on the
  review exactly as 008's admin form did.
- Login failures are uniform: unknown email, wrong password, and
  inactive account share one 401 body, and unknown emails still cost a
  hash verification.
- The initial password for an admin-created account is generated
  server-side, returned once in the create response, and stored only as
  a hash; the account must change it on first login.
- The closed site answers 404, not 401, on public routes; any valid
  session of any role passes the gate.
- Test fixtures log the shared TestClient in as an admin (the cookie jar
  carries the session), so prior tests' bare public GETs pass the site
  gate the same way a signed-in tester's browser does.
- `GET /api/v1/review/courses/{code}` was added beyond the two endpoints
  the feature spec listed: the reviewer's page needs the course facts,
  history, and SME names, and the admin SME routes are rightly closed to
  reviewers. It serves both roles, and the preview pages read it too.

**Known gaps**
- `grep -r ADMIN_TOKEN` is empty across code, config, and both
  `.env.example` files; the string still appears in this file's 001–008
  entries (append-only history) and in `current-feature.md` (replaced
  when 010 begins).
- An admin may still record a review on a reviewer's behalf through
  either surface; the record then shows the admin as recorder. 010
  should decide whether completion-era reviews must be recorded by an
  account holding the reviewer role.
- No rate limiting beyond the login attempt counter; no MFA, OAuth,
  password reset, or self-registration (016).
- Sessions are not tied to IP or user agent; both are recorded on the
  row but nothing checks them.
