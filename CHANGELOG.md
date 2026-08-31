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

## 010 — Enrollment, completion record, and certificate
Shipped: 2026-08-29

**What changed**
- `enrollments`: the record everything now hangs off. Created only by an
  admin (`POST /api/v1/admin/courses/{code}/enrollments` by participant
  email; 017 adds `source = 'purchase'`), on a published course, for an
  active participant, one active enrollment per (account, course).
  `expires_at` is stamped at creation as `enrolled_at + ENROLLMENT_DAYS`
  (365, 9.02.2(3)); status (active / expired / completed) is derived,
  never stored.
- Pinning: an enrollment records `{package_id: version}` at creation and
  the participant player and assessment serve those versions until it
  completes or expires. Unpublish stops new enrollments only; in-flight
  ones continue on their pin (the admin course page says so).
- Participant surface under `/api/v1/my` behind
  `require_role("participant")`, foreign enrollments 404: `/my/courses`
  (the post-login landing for the role), enrollment detail, per-lesson
  play/review/progress, the assessment, and the certificate download.
  Frontend routes `/my/courses`, `/my/courses/:id`,
  `/my/courses/:id/lessons/:packageId`, `/my/courses/:id/assessment`,
  reusing 006's Player (now with resume + throttled progress reports) and
  007's Assessment component. The admin/reviewer preview endpoints are
  untouched.
- Progress persistence, replacing 006's "nothing is persisted":
  `review_answers` (one row per question per enrollment, verdict
  snapshotted, re-answer updates — the 5.01.2 engagement record) and
  `lesson_progress` (`furthest_seconds`, monotonic).
- Assessment re-gating: `attempts.enrollment_id` gains its FK, the
  exactly-one-identity CHECK, and a one-open-attempt partial index.
  `start_for_enrollment` refuses a non-active enrollment (naming expiry or
  completion), unanswered review questions (named by lesson), and
  exhausted re-takes; `submit` past `expires_at` abandons the attempt
  unscored. Grading now reads the questions from the attempt's own
  recorded package versions. 007's failed-attempt no-feedback payload is
  re-asserted through the enrollment path.
- `completions`: one immutable row per passed enrollment, created inside
  the passing `submit` transaction — `completed_at` (= the attempt's
  `submitted_at`), `credit_awarded`, a per-year `YYYY-NNNNNN` certificate
  number, a verification token for 018, and `certificate_snapshot`
  freezing all eleven 9.01 items plus the awarding entity (9.01.1) at that
  moment. Nothing in the snapshot is ever re-read from live tables; the
  snapshot-immutability tests edit the course, sponsor, account, and
  state registrations after completion and prove the certificate text
  unchanged.
- Certificate rendering: `render(snapshot) -> bytes` in
  `app/services/certificates.py`, a one-page PDF from the snapshot alone
  (no db session). Stored once at `certificates/<number>.pdf`; the
  participant download renders lazily when the issuance fields allow and
  answers 409 "will be issued shortly" while they do not; admin has
  explicit Render/Download. Item 8 prints only when the snapshot carries
  it; item 5 prints "Not applicable (self study)".
- `certificates_overdue`: a sponsor-level warn finding
  (`readiness.sponsor_findings`) listing completions older than
  `CERTIFICATE_DEADLINE_DAYS` (60, 9.01) with no rendered PDF, shown on
  `/admin/sponsor` beside the launch-readiness panel.
- Admin course page gains Enrollments (enroll-by-email form, table) and
  Completions (table with certificate status, Render, Download) cards;
  `delete_course` refuses while any enrollment exists, whatever the
  course status.
- No change to `docs/course-package.md`; the contract is untouched.
- Tests: 31 new across `test_enrollments.py`, `test_completion.py`, and
  `test_certificates.py`; 168 total (was 137), all passing.

**Standards touched**
- 9.02.2(3) — `expires_at` stamped at enrollment, one year, enforced at
  assessment start and submit; new compliance row
- 6.01 — completion exists only as a row the passing submit transaction
  created, keyed to a participant account through the enrollment
- 6.01.2 — 70 percent, the no-feedback rule, and the question floors all
  preserved through the enrollment path; re-takes now a counted
  per-enrollment policy (new compliance row)
- 9.01 — the eleven-item snapshot frozen at completion; the 60-day
  delivery expectation reported, not enforced
- 9.01.1 — `sponsor_legal_name` in the snapshot is the awarding entity
  printed on the certificate
- 9.02.2(1) — `completions`, `review_answers`, `lesson_progress` retained
  per individual participant
- 7.01 — the certificate prints the course's one-fifth-rounded award and
  the verbatim `TIME_STATEMENT`
- 9.02 — every new table FK RESTRICT, no delete paths, course deletion
  refused with enrollments
- COMPLIANCE.md: 9.01, 9.01.1, 9.02, 9.02.2(1), and 6.01 rows appended;
  9.02.2(3) and 6.01.2 (re-takes) rows added.

**Decisions**
- PDF library: `fpdf2` (pinned 2.8.3) — pure Python, zero system
  dependencies, one small library for the one document produced.
  `reportlab` was rejected as far heavier than one page of centered text
  needs, and HTML-to-PDF routes (weasyprint, wkhtmltopdf) all drag in
  native dependencies. Its core fonts are Latin-1 only, so text is
  sanitized with replacement characters; re-rendering a snapshot
  reproduces the same text (asserted by extraction), while byte identity
  is not promised (PDF metadata carries a timestamp). `pypdf` is added as
  a test-side dependency to extract and assert that text.
- **`missing_fields` split.** 003 made `registry_status` a
  certificate-blocking missing field. That was right for the claim ("no
  certificate may say National Registry until it is true") and wrong for
  issuance: a sponsor not on the Registry may still issue a certificate —
  it simply cannot print item 8 — and Phase B's NASBA application needs a
  sample certificate before membership exists. So `missing_fields()`
  gains a `for_issuance` view (`name`, `legal_name`) that excludes
  `registry_status`; issuance gates on that view; item 8 gates on
  `may_claim_registry`, snapshotted at completion. 003's compliance row
  is appended to say so, and `/admin/sponsor` now shows the two lists
  separately.
- **Snapshot at completion, not at render.** If the sponsor's legal name
  is blank when a participant completes, the certificate that eventually
  prints will be missing it, because the snapshot is the truth and it was
  taken when the credit was earned. The fix is keeping the profile
  complete *before* opening the site — which the launch-readiness panel
  already says — not letting a later edit rewrite what a participant
  earned. `certificates_overdue` is the safety net, and the test suite
  proves the late-filled legal name is deliberately not on the PDF.
- **Pinning.** An enrollment is served the package versions it started
  on. Published courses are immutable (008), so a version change already
  implies unpublish → re-review → republish; in-flight participants keep
  what they enrolled on, and the certificate snapshot records exactly
  which versions. The trade-off is accepted: a correction re-exported
  mid-enrollment does not reach in-flight participants.
- **Re-take count.** 007 set `RETAKES_ALLOWED = True` (unlimited) when no
  enrollment existed to count against. 010 makes it the number it always
  wanted to be: 3 re-takes per enrollment after the first sitting —
  sponsor's discretion under 6.01.2, exhausted-retake starts refused
  naming the constant, preview attempts never counted. 007's test was
  updated to assert against the constant rather than the literal `True`;
  011's policies page must disclose the number.
- Certificate numbers come from a per-year counter table read under a row
  lock (`certificate_sequences`), with the unique constraint as backstop;
  the verification token is 32 random bytes hex, stored for 018.
- The completion re-reads nothing, with one exception by design: the
  render *gate* checks the live issuance fields (today's paperwork),
  while everything printed comes from the snapshot.

**Known gaps**
- Pinned lessons are ordered by the course's current position for the
  same lesson (falling back to the manifest position), because JSONB does
  not preserve key order; reordering lessons mid-enrollment would reorder
  an in-flight participant's list, though published courses being
  immutable makes that reachable only through unpublish.
- The participant can still play lessons and answer review questions on
  an expired or completed enrollment; only the assessment is gated. The
  engagement record may therefore gain rows after completion.
- Certificate delivery is a download; email delivery and the public
  verification page that resolves the stored token are 018.
- Out-of-scope hits for 011: the policies page must state the re-take
  policy (`RETAKES_ALLOWED`) and the refund policy; the program
  evaluation (4.04) attaches to the completion row that now exists;
  everything else the audit bundle needs (attempts, answers, progress,
  completions, snapshots, the credit record) is already in rows.

## 011 — Program evaluation, policies, retention, and the audit bundle
Shipped: 2026-08-29

**What changed**
- `evaluations` (4.04.1): one per completion, the four applicable elements
  on a 1–5 scale with CHECKs, `instructors_effective` constrained null
  (self study; the column exists so the record visibly answers item 5 as
  not applicable), comments, and an `objectives_snapshot` copied from the
  completion's pinned packages. The exact prompt wording is code-versioned
  in `app/constants/evaluation.py`. Solicited on the result page and
  `/my/courses` for `SOLICIT_UNTIL_DAYS` (30) after completion; skippable,
  refusable once, and the certificate never waits on it.
- `evaluation_reviews` (4.04.2): dated, by account, with the summary
  snapshotted as of the review and an `informed_developer` attestation.
  The `evaluation_review_due` warn finding (in `readiness.check` and the
  sponsor panel) fires when an evaluation has waited more than
  `EVALUATION_REVIEW_DAYS` (90) without a review.
- `policy_versions` (8.01 items 8–10): append-only, effective-dated; the
  current version of a kind is derived, never marked. Public `/policies`
  page and payload behind the same gate as the catalog; the course page
  links it. The re-take policy is rendered from `RETAKES_ALLOWED` and
  `PASSING_PCT` (010's disclosure debt paid); the item 11 sponsor
  statement is `NASBA_SPONSOR_STATEMENT`, rendered only under
  `may_claim_registry`.
- New site-open refusal: `site_open_blockers()` in `app/services/site.py`;
  `set_site_mode(open)` now refuses (422) naming each policy kind with no
  current version. 009 let the flip through unchecked. `/admin/sponsor`
  gains the launch findings panel and a Policies card.
- `RETENTION_YEARS = 5` (`app/constants/retention.py`, 9.02 quoted);
  `retain_until` derived in `app/services/retention.py`, shown on the
  admin completions table and in every bundle record with a
  `completed_at`. Nothing deletes at the boundary.
- 4.05.3 items 1 and 4: the public course payload gains `outline`
  (lesson titles with their objectives, no new storage), rendered as
  "What this course covers"; `/how-it-works` serves instructions whose
  numbers are read from the constants that enforce them, linked from
  `/my/courses` and the course page.
- The per-course audit bundle (`app/services/audit_bundle.py`): the seven
  9.02.2 elements as directories in one zip with a README that quotes and
  maps each, `bundle.json` listing every file with sha256 and size, CSVs
  in UTF-8 with ISO 8601 UTC timestamps, and every package version ever
  attached or pinned under `7-materials/`. Videos by reference unless
  `include_video`. Exports are stored at `audits/<code>/<timestamp>.zip`
  and logged append-only in `audit_exports`; the admin course page gains
  the Audit bundle card (generate, history, download).
- Certificate font fix: DejaVu Sans (regular, bold, oblique, with its
  license) vendored under `backend/app/assets/fonts/`; `render` embeds
  them and no longer sanitizes to Latin-1, so names like "Nguyễn
  Michałowski" print and extract unchanged. Latin-1 text renders
  identically.
- No change to `docs/course-package.md`.
- Tests: 31 new across `test_evaluations.py`, `test_policies.py`,
  `test_audit_bundle.py`, and the font test in `test_certificates.py`;
  199 total (was 168), all passing.

**Standards touched**
- 4.04, 4.04.1 — evaluations solicited from participants for the overall
  program, the five elements answered (item 5 as not applicable)
- 4.04.2 — periodic review of results recorded, snapshotted, and reported
  when overdue; informing the developer is a named-and-attested step
- 4.05.3 — items 1 and 4 built; items 2–3 recorded as the ROADMAP
  improvement note naming both repos
- 8.01 items 8–11, 8.01.1 — the three policies formalized, published, and
  made available; the sponsor statement gated on `may_claim_registry`;
  the site cannot open without them
- 9.02 — the five-year period is now a named constant with a derived
  `retain_until`; existing row's gap replaced
- 9.02.2 (1)–(7) — the full documentation set exportable per course;
  9.02.2(5) and (6) rows added
- 9.01 — row appended: the Unicode font
- COMPLIANCE.md: rows added/amended as above.

**Decisions**
- 30 days of soliciting and 90 days of "periodically" are superCPE's own
  numbers, said so in the constants' docstrings and the compliance rows;
  NASBA fixes neither.
- Policies are append-only effective-dated versions, not one editable
  text: a participant who enrolled under an old policy may hold the
  sponsor to it, so every version stays readable and the current one is
  derived (`effective_at <= now()`), never marked. The re-take policy and
  the sponsor statement are deliberately NOT rows — they render from the
  constants that enforce them, so the published policy can never disagree
  with the code.
- The site-open refusal blocks only on missing policies (block-level
  launch findings). `evaluation_review_due` is a warn beside them: an
  overdue evaluation review must never be able to keep the site closed,
  because its fix has nothing to do with participant-facing readiness.
- Videos are included in the bundle by reference (storage key,
  content_hash, duration in `video.txt`): the zips stay small enough to
  generate on request, the keys are write-once so the reference stays
  good, and `include_video=true` exists for the reviewer who wants the
  bytes.
- The bundle's `6-descriptive/course.json` is built by the same
  `public_detail` function the public route serves, so the two can never
  disagree.
- The Standards' effective-date paragraph (March 1, 2027 for new self
  study programs) is recorded nowhere in code, concluded deliberately:
  superCPE builds to the 2026 Standards uniformly from day one, so the
  transition dates gate no behavior. Noted in ROADMAP.
- Markdown on the policies and instructions pages is rendered by a ~90
  line `SimpleMarkdown` component (headings, lists, bold, paragraphs, all
  as text nodes) rather than a Markdown dependency; admin-authored policy
  text does not justify one.

**Known gaps**
- Evaluation results reach the developer as an attestation checkbox and a
  named developer on the admin summary page; actual delivery is email
  (018).
- 4.05.3 items 2 (keyword search) and 3 (glossary) are unbuilt content
  features; the ROADMAP improvement note specifies the course-package
  contract change (`manifest.glossary[]`) and the video-tool authoring
  feature they need.
- An unrendered certificate appears in the bundle as its snapshot JSON
  only; the PDF joins once rendered ("every rendered certificate").
- Bundle CSV rows for preview attempts name the participant as
  "(preview)" — they are retained attempts on the course, and hiding them
  from the record would be worse than labeling them.
- The five-year retention date is stated, not enforced, and storage is
  still local disk; durability is 012 (whose ROADMAP entry now lists all
  three write-once key prefixes: `packages/`, `certificates/`,
  `audits/`).

## 012 — Spaces storage, production config, and deployment to superCPE.com
Shipped: 2026-08-30

**What changed**
- `SpacesStorage` in `backend/app/storage.py`: the second implementation
  of 002's `Storage` protocol, boto3 against the Spaces endpoint, private
  bucket, `ContentType` set, no public ACL ever. The protocol gained
  `url_for(key, expires_seconds)`; under `spaces` that is a presigned GET
  living `VIDEO_URL_SECONDS` (3600, `app/constants/storage.py`), under
  `local` the existing `/api/v1/media/` path — and the `/media/` route is
  mounted only when `STORAGE_BACKEND=local`. Certificate and audit
  downloads keep streaming through the API behind the session check.
- Production settings: `ENV` (`dev`|`prod`); in `prod` boot refuses, every
  violation listed at once, unless cookies are Secure, `CORS_ORIGINS` is
  exactly `https://supercpe.com`, `DATABASE_URL` carries
  `sslmode=require`, `STORAGE_BACKEND` is `spaces`, and secrets are ≥ 32
  bytes.
- `deploy/`: API `Dockerfile` (Python 3.12 slim, ffmpeg, non-root,
  migrations as a separate entrypoint command), `Dockerfile.web` (Vite
  build served by Caddy built with xcaddy), `Caddyfile` (automatic TLS,
  `www` → apex, HSTS, `/api/*` proxied, login rate limit 10/min/IP),
  `docker-compose.yml` (caddy + api; Postgres is the managed cluster),
  `deploy.sh` (checkout, build, migrate, restart, poll `/health` for the
  new sha), `rollback.sh`, `backup.sh` (nightly `pg_dump` custom format,
  gzip, upload to `backups/<date>.dump.gz`, keep 90 days + one per month,
  stamp `backups/LATEST`), `env.production.example`.
- `GET /api/v1/health` returns `{version, env, database, storage,
  ffprobe, last_backup_at}`, 503 if any component errors; `version` is
  the git sha baked at build, storage is a HEAD on `health/sentinel`,
  `last_backup_at` reads `backups/LATEST`.
- `docs/OPERATIONS.md`: security posture in one place, then first deploy,
  routine deploy, rollback, restore (snapshot path and dump path), secret
  rotation, course re-ingest, and per-field `/health` triage — each
  executed at least once during this feature.
- Tests: 28 new against `moto`'s in-process S3 mock (storage round-trip,
  presigning, no-ACL, prod config refusals, 503 with the failing
  component named, `/media/` absent under `spaces`). 227 at the 012
  build; 252 at today's checkout with 013's, all passing.
- **First deployment, 2026-08-30**: live at https://supercpe.com in
  `coming_soon` mode over TLS, empty database, all ten migrations clean,
  every `/health` component ok — sha `bd7a4e83` (build), then `62de030`
  (post-deploy runbook fixes). Infrastructure as built is recorded in the
  operator's handoff outside the repo: NYC3 droplet (4 GB), managed
  PostgreSQL 16, bucket `supercpe-prod-nyc3` with a bucket-scoped
  Limited Access key, ufw 22/80/443, secrets in `/srv/supercpe/.env`
  mode 600, backup cron 03:15 UTC.
- **Rollback exercised**: `62de030` → `bd7a4e8` → `62de030`; all four
  health components ok at every step, the health poll matched the
  expected sha in both directions, no migration between the shas.
  Incidental finding worth keeping: when `.env` was mis-set during the
  drill, `deploy.sh` failed safe — it stopped at the migration step and
  never touched the running API, exactly as the runbook claims. First
  real test of that behavior.
- **Restore drill, 2026-08-30, 14:46–15:04 UTC, 18 minutes**:
  `backups/2026-08-30.dump.gz` → scratch db `supercpe_restore_drill`;
  `alembic_version` `c8a15d20e9b4` both sides, 24 tables both sides, 1
  account both sides; the completions/`certificates/` cross-check was
  vacuous on the empty database and is recorded as such. Dated in
  `docs/OPERATIONS.md`. The drill surfaced runbook errors — notably a
  step that sent the operator to repoint production's `.env` at the
  scratch database, plus the `postgresql+psycopg` vs plain `postgresql`
  scheme, the control panel's show/hide link contaminating a copied
  password, a step with no commands, and no cleanup step — all fixed in
  `263a6b7`.
- **Acceptance walkthrough**: package upload `ASC606-CON-01` v1 → object
  at `packages/ASC606-CON-01/v1/video.mp4`, preview played (206 Partial
  Content, video/mp4) via a presigned URL (AWS4-HMAC-SHA256,
  `X-Amz-Expires=3600`) that re-curled 403 after expiry; audit bundle
  generated from the draft course →
  `audits/ASC606-CON/20260830T155309757977Z.zip`, 12,165 bytes, in
  history and downloadable; secrets grep clean (credential values appear
  nowhere; only variable names and the example file).

**Standards touched**
- 9.02 — retained records now live in one managed database (daily
  snapshots) and one private bucket (write-once prefixes `packages/`,
  `certificates/`, `audits/`), with a nightly logical dump and an
  executed, dated restore drill
- 4.05.2 — `/api/v1/health` is the monitoring; the external uptime
  monitor on it is still to be set up (gap below)
- 9.01 — certificates persist in `certificates/` under the backup policy
  and stay retrievable through the API
- 9.02.2(7) — program materials under `packages/` on the same footing
- COMPLIANCE.md gained the three 012 rows at build time, and the
  2026-08-30 correction row: the original gap said Spaces has no object
  versioning; Spaces does (API-only enable) — it was merely not enabled,
  which became 013's opening task.

**Decisions**
- Managed Postgres over a container: backups are a 9.02 control, and a
  managed cluster's daily snapshots plus point-in-time recovery beat
  anything hand-rolled on the droplet.
- Caddy over nginx: automatic Let's Encrypt TLS in four lines. The login
  rate limit is the mholt/caddy-ratelimit plugin compiled in with
  xcaddy — a documented, justified build step rather than a switch to
  nginx for one directive.
- `boto3` because Spaces is S3-compatible and boto3 is the reference
  client; hand-rolling SigV4 presigning would be more code and less
  trustworthy. `moto[s3]` test-only: exercises `SpacesStorage`,
  presigning, and backup pruning through real boto3 calls with no
  network and no bucket. (Both justified in `backend/requirements.txt`.)
- Presigned video URLs live one hour (`VIDEO_URL_SECONDS = 3600`): long
  enough for any lesson, short enough that a shared link dies the same
  afternoon.
- There is no application `SECRET_KEY`: sessions are database rows keyed
  by token hash (009), so rotation is `DELETE FROM sessions`, not a key
  ceremony.
- Production started from an empty database by design. The dev
  database's fictitious reviewer, test participant, and test policies
  never left the laptop; ASC842-PCX is re-ingested and reviewed for real
  in 014.
- PostgreSQL 16 was a deliberate pin, not the default (DigitalOcean
  preselects 18): 16 already lives in `docker-compose.yml`,
  `deploy/backup.sh`'s `postgres:16 pg_dump`, and the restore
  procedure's `postgres:16 pg_restore`, and `pg_dump` aborts on a newer
  server major — drift would break the nightly backup silently, with
  `last_backup_at` going stale as the only signal. Cluster reports
  16.15.
- The droplet is 4 GB, not the spec's 2 GB: `docker compose build` runs
  on the box and is the memory-hungry step (xcaddy alone took 269 of the
  first build's 294 seconds).
- Acceptance item 3 was run with the sample package `ASC606-CON-01`, not
  `ASC842-PCX-01`, keeping production's `packages/` clean for 014's real
  re-ingest.
- Acceptance item 3's `/media/` wording was unfalsifiable as written:
  `/media/anything` returns the SPA shell, as does every unmatched path.
  The real check is `/api/v1/media/anything` → 404, which is how
  OPERATIONS.md words it.

**Known gaps**
- The external uptime monitor (4.05.2) is not yet set up; its login line
  in OPERATIONS.md "Who and where" is empty until it is.
- Two findings from the first deploy are fixed in the runbook
  (`62de030`) but worth knowing: a panel-created database is owned by
  `doadmin`, not the panel-created user, so `alembic upgrade head` fails
  on a permission error until `ALTER DATABASE supercpe OWNER TO
  supercpe`; and `GIT_SHA` falls back to `dev` on manual compose
  commands, so every runbook command is prefixed with an export.
- `deploy.sh`'s health poll can exit non-zero on a *correct* first
  deploy (the sentinel is written after), documented in the runbook.
- Object versioning was not enabled by this feature (the corrected
  COMPLIANCE row explains why it is its own feature); 013 built it.
- The sponsor profile is deliberately blank — no legal entity exists
  yet — so certificate issuance is correctly blocked by
  `missing_fields`; no error on the blank profile.
- The session cookie's Secure/HttpOnly flags are enforced by config and
  asserted in tests but were not re-inspected in the browser during
  acceptance; the `www` redirect was likewise not explicitly verified.
- Ops debt recorded in ROADMAP's Phase B backlog: rotate the `doadmin`
  and starter-admin passwords (exposed in a chat transcript during
  setup) and apply the droplet's pending OS security updates.

## 013 — Durability of retained records
Shipped: 2026-08-30

**What changed**
- `deploy/bucket-setup.py`: run once, by hand, with a temporary Full
  Access Spaces key passed only as `SETUP_SPACES_KEY`/`SETUP_SPACES_SECRET`
  environment variables (never read from `.env`). Enables object
  versioning on the bucket, puts a lifecycle configuration with exactly
  one rule — expire noncurrent versions under `backups/` after
  `BACKUP_NONCURRENT_DAYS` (7, `app/constants/storage.py`, docstring
  explaining why that prefix alone) — prints both read-backs, exits
  non-zero if either does not read back as set. Idempotent.
- Versioning as an enforced control, not a setting:
  `SpacesStorage.versioning_enabled()` (GetBucketVersioning with the
  runtime Limited Access key, which can read but not change it); in
  `prod` the app refuses to boot while versioning is not `Enabled`
  (`ensure_bucket_versioning`, called from `app/main.py`); `/health`
  gains `bucket_versioning`, contributing to the 503 rule.
  `LocalStorage` reports ok — there is nothing to version.
- Off-site mirror: `OFFSITE_ENDPOINT/REGION/BUCKET/KEY/SECRET` config
  (all-or-nothing; secret ≥ 32 bytes; in `prod` the endpoint must not be
  DigitalOcean — that would be a second bucket, not a second provider);
  `app/services/offsite.py` with `mirror_backup(date)` (copies the
  night's dump, stamps `backups/LATEST` off-site and `backups/OFFSITE`
  in the primary) and `mirror_prefix` (copies every `certificates/` and
  `audits/` object absent or ETag-changed off-site, never deletes);
  `python -m app.cli mirror-offsite` called by `backup.sh` only after
  the primary upload is stamped, so a dead off-site provider exits
  non-zero and is logged but can never make `last_backup_at` stale and
  mask the primary as the problem (verified by acceptance test).
  `/health` gains `last_offsite_backup_at` — `null` when unconfigured or
  never run, and never part of the 503 rule; staleness past ~26 hours is
  the uptime monitor's alarm, like `last_backup_at`.
- Prune under versioning: `backups.py` pruning still removes dumps from
  the current listing; a moto test with versioning enabled asserts
  pruned dumps are gone from the current listing and present as
  noncurrent versions (which the lifecycle rule then reclaims).
- `docs/OPERATIONS.md`: new "Bucket versioning" section (recovering a
  prior object version by `VersionId`; the runtime key cannot change
  versioning or lifecycle) and "Off-site copy" section (what is
  mirrored, restore path); `deploy/env.production.example` gains the
  five `OFFSITE_*` lines marked optional with the different-provider
  rule. The 012 runbook corrections folded in: why the `pg_restore`
  container reaches the VPC host (NAT through the droplet, the trusted
  source); the scratch-database ownership trap and its `ALTER DATABASE`;
  `--user $(id -u)` on the restore's compose run; the drill-record
  wording ("into a scratch database", never production) with
  non-vacuous verifications for an empty database.
- Tests: 252 pass (was 227), covering the boot refusal, the `OFFSITE_*`
  all-or-nothing and same-provider rules, mirror copy/never-delete
  semantics, both stamps, the two `/health` fields, `bucket-setup.py`
  idempotency and read-back failure, and prune-under-versioning.

**Standards touched**
- 9.02 — the bucket itself now keeps every prior version of every
  retained object (once enabled — see gaps), and the off-site copy
  exists in code for the day a provider is chosen
- 9.02.2(1)–(7) — the audit bundles under `audits/` are the first
  mirrored prefix; `packages/` deliberately is not
- 9.01 item 2 — certificates under `certificates/` are the second
  mirrored prefix
- COMPLIANCE.md gained the four 013 rows at build, and today a
  correction row recording that the mirror is built but dormant.

**Decisions**
- Boot refuses on versioning-off but only reports on offsite-missing.
  Versioning is a control someone can switch off in a control panel
  while the application keeps running normally — exactly the control
  that gets found off during an audit, so the application will not run
  without it. A missing off-site provider is a state the design
  explicitly allows while one is chosen or replaced, and it must never
  take the site down.
- `packages/` is not mirrored: videos are large, and every exported zip
  also exists in video-tool's `dist/` on the machine that produced it.
  Recorded as a ROADMAP improvement note, not built.
- One lifecycle rule, `backups/` only: a nightly dump superseded by the
  next night's has no retention value beyond a week, while every other
  prefix is 9.02 material whose noncurrent versions are never expired.
- **Operator decision, 2026-08-30: no second-provider bucket for now.**
  The mirror ships dormant — `OFFSITE_*` unset,
  `last_offsite_backup_at: null` by design. This entry therefore cannot
  record which provider was chosen or what a real second provider
  honored, because none was; the standing exposure (originals,
  snapshots, and dumps all at DigitalOcean) is recorded in the
  COMPLIANCE correction row and the ROADMAP note. Turning the control
  on later is five `.env` values and one `backup.sh` run, no code.

**Known gaps**
- The off-site copy is not running (above); provider-level failure
  still takes the originals and every backup together.
- `bucket-setup.py` has not yet run against the real bucket, so
  versioning is verified against moto only and whether DigitalOcean
  honors `NoncurrentVersionExpiration` with a prefix filter on the real
  API is unverified. Until it runs, 013 must not deploy — the `prod`
  boot refusal would stop the API — so production still runs `62de030`.
  Running it (and recording the read-back) is 014's first prerequisite.
- The bucket-layer recovery drill (write `health/sentinel` twice,
  recover the older by `VersionId`) has not run; its record line in
  `docs/OPERATIONS.md` is empty. Also folded into 014's prerequisites.
- Restoring *from* the off-site copy is documented but undrilled (a
  Phase C item), and moot while the mirror is dormant.

## 013 correction — the 2026-08-30 boot-refusal outage
Shipped: 2026-08-30

A statement of fact correcting the deployment record; the 013 entry
above stands as written.

**What happened**
- 013's known gaps said it must not deploy before `deploy/bucket-setup.py`
  had run against the real bucket. On 2026-08-30, `ad00797` (013's code
  plus the 012/013 changelog docs) was deployed before the script had
  run. The `prod` boot refusal (`ensure_bucket_versioning`) fired exactly
  as designed — and took production down: containers up, uvicorn workers
  dead, Caddy returning 502. `deploy.sh` fails safe on a bad migration,
  but had no equivalent gate for a boot refusal; the old version was
  already stopped by the time the guard fired.
- The documented remedy proved unrunnable from the environment the
  runbook assumed, for four reasons:
  1. The droplet host has no `python` and no boto3; the script was
     written as if it runs on the host.
  2. It was not in the api image either — the Dockerfile copies only
     `backend/`, so `docker compose run api python deploy/bucket-setup.py`
     could not see it.
  3. Bind-mounting it to `/tmp` broke its `sys.path` bootstrap
     (`ModuleNotFoundError: No module named 'app'`) — the path insert is
     computed relative to `__file__` for the repo layout.
  4. When the operator reached the S3 API by hand, the key produced
     `AccessDenied` on `PutBucketVersioning`. The runbook said "temporary
     Full Access key" but never said that a bucket-scoped key, even with
     full object permissions, cannot call bucket-configuration
     operations — only an All Permissions (all-buckets) key can.
- Outage window and recovery path taken (operator records at
  stabilization, per 014a acceptance step 0 — rollback to `62de030` if
  still down): ____________________

**Standards touched**
- 9.02 — the control itself behaved as built; the operability around it
  failed. No change to what any locator requires.

## 014a — Make the versioning control deployable
Shipped: 2026-08-30

**What changed**
- `python -m app.cli bucket-setup`: the logic of `deploy/bucket-setup.py`
  moved into the api image (`backend/app/cli.py`); the standalone script
  is deleted — git history retains it, and this entry records the move.
  Behavior is 013's spec unchanged: endpoint, region, and bucket from
  the normal settings (the container's mounted `.env`); credentials
  **only** from `SETUP_SPACES_KEY`/`SETUP_SPACES_SECRET`, non-zero with
  a clear message if unset; enables versioning, puts the one `backups/`
  lifecycle rule, prints both read-backs, non-zero if either does not
  read back as set; idempotent. New: on `AccessDenied` the error says in
  plain words that a bucket-scoped key cannot perform
  bucket-configuration calls and that an All Permissions key is
  required. The documented invocation is one `docker compose run` line
  with no mounts and no host Python (`docs/OPERATIONS.md`).
- `python -m app.cli preflight`: runs, without starting the server,
  every check that would refuse boot — `boot_violations` (the 012
  validations, same code path, every violation at once),
  `ensure_bucket_versioning` when `STORAGE_BACKEND=spaces` (an
  unreachable bucket or failed read is a named failure, not a crash or
  a pass), and `ensure_ffprobe_available`. Exit 0 when the app would
  boot; non-zero with the same messages the boot refusal would print.
- `deploy.sh`: after building and **before** migrations or touching the
  running containers, runs `preflight` as a one-off container from the
  newly built image against production's env file; non-zero aborts the
  deploy with the old version still serving — the same fail-safe shape
  as the migration step, extended to boot refusals. Preflight runs
  before migrations on purpose: it validates config and bucket state,
  which do not depend on schema, so an abort leaves nothing to
  reconcile. `rollback.sh` execs `deploy.sh` and therefore carries the
  identical gate (recorded in its header comment).
- The `ensure_bucket_versioning` refusal message, the
  `BACKUP_NONCURRENT_DAYS` docstring, and `docs/OPERATIONS.md` now name
  the CLI subcommand and the **All Permissions** key requirement
  (console path, `read -rs`, delete-and-unset after the read-backs).
  OPERATIONS.md also gained the dated read-back record table (evidence
  for whether DigitalOcean honors `NoncurrentVersionExpiration` with a
  prefix filter — 013's open question) and the what-a-preflight-abort-
  looks-like paragraph under the deploy procedure; the bucket-layer
  recovery-drill record line stays where 013 put it.
- Tests: 260 pass (was 252). 013's script tests ported to the CLI
  (versioning + the one rule, idempotency, read-back failure) plus the
  unset-credentials refusal and the AccessDenied message naming the
  key-scope cause; preflight exit codes under a bootable prod config
  (moto), versioning off, an unreachable bucket, config violations
  listed at once, and the local-storage skip; a grep-level assertion
  that `deploy.sh` preflights before it migrates.

**Standards touched**
- 9.02 — no locator's requirement or satisfaction changed: the guard
  stays, versioning remains the bucket-layer control 013 built. This
  feature makes the control deployable and makes its failure mode a
  failed deploy instead of an outage. COMPLIANCE.md gained a correction
  row pointing the 013 row's `deploy/bucket-setup.py` reference at the
  CLI subcommand.

**Decisions**
- Removing or weakening `ensure_bucket_versioning` was considered and
  rejected (the alternatives disable every prod guard or delete the
  control 013 exists to enforce). What changed is that a failed guard
  is caught by the gate before the old version stops.
- `preflight` also checks ffprobe: the feature named the config
  validations and the versioning guard, but ffprobe is the third boot
  refusal in the lifespan, and a gate that skips it would still let a
  broken image turn into an outage. Same code path, no duplicated rule.
- `preflight` checks versioning whenever `STORAGE_BACKEND=spaces`, not
  only when `ENV=prod`, per the feature spec; in production the two
  coincide (prod requires spaces).

**Known gaps**
- Acceptance steps 0–4 are the operator's, on the droplet, and had not
  run at build time: stabilization and the outage window (the 013
  correction entry above carries its fill-in line), the real
  `bucket-setup` run and its two read-backs (the OPERATIONS.md table),
  the sentinel recovery drill (013's empty record line), the 014a
  deploy with preflight observed passing, and the negative gate test
  against a nonexistent bucket. Until the real run, versioning and the
  lifecycle rule remain verified against moto only.
- The off-site mirror stays dormant (2026-08-30 operator decision);
  014 proper (ASC842-PCX re-ingest and real review) is unblocked by
  this feature, not part of it.

## 015 — Coming-soon landing page and waiting list
Shipped: 2026-08-30

**What changed**
- `waiting_list` table (migration `e5b7d9a3c1f8`): name, email
  (lowercased/trimmed, unique), two-letter state of licensure, optional
  firm, `source` (default `coming_soon`, for 021 to tell early signups
  apart), and a soft delete (`removed_at`/`removed_reason`). The model
  docstring says in so many words that these rows are **not CPE
  records** — no participant, no enrollment, no `RETENTION_YEARS` — and
  that the soft delete is deliberately different from the 9.02
  accounts rule. Jurisdiction codes live in
  `app/constants/jurisdictions.py` (the 55 US boards), placed for 020
  to reuse.
- Two public routes carved out of the 009 gate, allowed **only** while
  `site_mode` is `coming_soon` and 404 once it is `open`
  (`backend/app/routers/landing.py`): `GET /api/v1/landing` (sponsor
  display name, `may_claim_registry`, `policies_published` — no field
  exists for course facts, credit figures, objectives, or prices) and
  `POST /api/v1/waiting-list` (422 in the standard `{"errors": [...]}`
  shape; a repeat email is an idempotent 200 with `created_at`
  unmoved; a signup against a removed row clears the removal and
  re-adds). Spam controls: a hidden honeypot field answered with the
  identical 200 that stores nothing, and a Caddy rate limit on the
  signup POST mirroring the login rule (`deploy/Caddyfile`).
- 009's router-table walk now exists as
  `test_router_walk_closed_site_hides_everything_not_intentionally_public`
  (`backend/tests/test_site.py`): every route anonymously in
  `coming_soon` must answer 401 or 404 unless listed in
  `INTENTIONALLY_PUBLIC`, where both 015 routes are marked with their
  feature number — an unguarded new route now fails a test by name.
- The landing page (`frontend/src/pages/ComingSoon/`), served by
  `SiteGate` for **every** public and unmatched path while
  `coming_soon` (the catch-all route now passes the gate too): who
  superCPE is, one plain paragraph on the ASC 842 practical-expedients
  course in preparation, the sentence promising full program details
  before registration opens (the page's honest substitute for 8.01),
  and the waiting-list form with a one-message email-use statement.
  No credit number, field of study, level, prerequisites, or price;
  no `/login` link; the Registry block renders only behind
  `may_claim_registry` (false), and the footer links the policies
  pages only when all three are published (on production they are
  not). No new dependency, no analytics, no third-party script.
- Admin surface: `/admin/waiting-list` (count, searchable table,
  Remove with optional reason) over
  `GET/POST /api/v1/admin/waiting-list...` and
  `GET /api/v1/admin/waiting-list/export.csv` — UTF-8, header row,
  ISO-8601 timestamps, active entries only, generated on request,
  never written to Spaces and not part of the 9.02 audit bundle
  (`backend/app/routers/admin_waiting_list.py`). The routes sit under
  `/admin` and are therefore swept by 009's guarded-route walk
  automatically.
- Docs: COMPLIANCE.md gained the 8.01 no-descriptive-material-by-design
  row, the 8.01.1 policies-footer row, and the 9.01-item-8 row
  recording the landing page as the first public surface under 003's
  Registry-claim rule; OPERATIONS.md gained the waiting-list section
  (count, export, open-closes-permanently); ROADMAP.md records 015
  shipping before the deferred 014.
- Tests: 272 pass (260 at the 014a checkout).

**Standards touched**
- 8.01 — deliberately not satisfied and deliberately not half-satisfied:
  the page discloses none of the eleven items because partial
  disclosure reads as descriptive material; the payload has no field to
  carry a course fact, and a key-set test enforces it. 016 owns the
  full disclosure.
- 8.01.1 — websites are a named disclosure channel; the page's answer
  is the published-before-registration sentence, and the policies
  footer renders links only when the 011 policies actually have current
  versions.
- 9.01 item 8 (003's Registry-claim rule) — first public surface that
  reads `may_claim_registry`; a test fetches the landing response and
  asserts "National Registry" is absent while it is false.

**Decisions**
- The signup response body is one constant message for first, repeat,
  and honeypot submissions, so the response never reveals whether a row
  exists or was created.
- A signup against a removed row refreshes name/state/firm but keeps
  the original `created_at` — the row records when they first asked.
- Waiting-list email validation is the same minimal shape check
  accounts use (auth service), not a deliverability check; the one
  invitation 021 sends is the real test of the address.
- The admin remove endpoint returns the refreshed listing (same shape
  as the site-mode change returning its log), so the page repaints in
  one round trip.

**Known gaps**
- Acceptance 6–7 (deploy via `deploy.sh` with preflight passing, a real
  submission on https://supercpe.com, the by-eye check of the deployed
  page) are the operator's, on the droplet, and had not run at build
  time. **The 015 prerequisite is also not yet true**: as of this entry
  production `/health` reports sha `62de030` (the pre-013 rollback)
  with no `bucket_versioning` field — 014a's operator steps
  (`bucket-setup` against the real bucket, then deploying the 014a
  sha) have to land first, and 015 deploys after them through the same
  preflight gate.
- The footer's policies links, when the policies are eventually
  published while still `coming_soon`, would lead to a `/policies` page
  that is itself behind the 009 site gate (it renders the landing page
  again for anonymous visitors). Harmless today — on production the
  links are absent because nothing is published — and 016 replaces this
  page entirely; noted so nobody reads the footer code as a gate hole.

## 016 — Public catalog and course pages with full 8.01 disclosure
Shipped: 2026-08-31

015's stale known-gap paragraph is closed: the operator ran 014a's
bucket-setup and deploy steps and production reached `b0b8850` healthy on
2026-08-30, and 015's acceptance 6–7 (the deploy through the preflight
gate, a real submission on supercpe.com, and the by-eye browser check of
the deployed page) were completed by Dane on 2026-08-30.

**What changed**
- Disclosure completeness as a named check: `missing_items` in
  `backend/app/services/disclosure.py` returns every applicable 8.01
  item (by number and name) that is missing or unusable. Items 2 and 11
  are constants and cannot fail; item 11 is counted only while
  `may_claim_registry` is true ("if an approved NASBA sponsor" is the
  Standard's own condition); item 3 is unusable — not just missing —
  when 005's stored credit is stale or the award is below the minimum
  awardable; items 4 and 6 fail on blank, never on a stored "None";
  items 8–10 fail when the 011 policy kind has no current published
  version.
- Publish gate: `courses.publish` now also refuses with one error per
  missing item, each naming its 8.01 number, in the same 422
  `{"errors": [...]}` shape. A course that cannot disclose completely
  cannot be published. Unpublishing is untouched. A published course
  that would now fail (dev only; production starts empty) is flagged on
  the admin course view — a visible warning under Publish and one
  finding per item under Readiness — never auto-unpublished.
- Registration-and-attendance policy (item 8): **011 already built it**
  — `registration` is one of the three `POLICY_KINDS` with the same
  append-only effective-dated versions, so nothing was added. The
  site-open gate **iterates** policy kinds (`missing_kinds` walks
  `POLICY_KINDS`), so it already included the registration policy and
  needed no update.
- Public payload, final shape (`backend/app/routers/courses.py`,
  `backend/app/schemas/course.py`): `program_type` (item 2, always the
  `PROGRAM_TYPE` constant — "Self study", never "QAS Self Study") joins
  both payloads; the detail payload carries `registration_policy`,
  `refund_policy`, and `complaint_policy` as named `PolicyLink` fields —
  a link (`/policies#<kind>`, anchored on the policies page) plus the
  current version's effective date, never inlined policy text — and
  `sponsor_statement` (item 11) only while claimable: the key is absent,
  not null, while `may_claim_registry` is false, enforced by the model's
  own serializer so the route and the audit bundle's
  `6-descriptive/course.json` cannot disagree. `policies_url` is
  removed; the 4.01 `last_documented_date` was already served and is now
  asserted by the key-set test. A course whose stored credit is stale is
  refused outright — omitted from the catalog, 404 on detail — instead
  of rendering with a hole where item 3 belongs. `public_detail` now
  takes `db`; the item 11 gate moved into
  `services.policies.sponsor_statement`, the one place it is applied.
- Site-open gate extension: `launch_findings` blocks
  `coming_soon → open` while no published course passes the disclosure
  check — one finding when nothing is published at all, otherwise one
  itemized finding per published course, same shape as the 011 policies
  refusal.
- Frontend: the root path renders the catalog (the 001 walking-skeleton
  home page is retired; SiteGate verified to stop serving the landing
  page at open — `site_mode === "open"` returns children before
  `ComingSoon` is considered). Catalog cards add the recommended credit.
  The course page renders the items in the Standard's stable order —
  description, objectives/outline, a Program details list in item order
  2–6, the three policy links with effective dates, lessons, a visibly
  reserved Registration section with no dead button (017's future home),
  the conditional item 11 statement, and the provenance line with the
  4.01 date. Everything renders from the payload; the page adds no
  course fact of its own.
- Tests: 288 pass (272 at 015). New `backend/tests/test_disclosure.py`:
  the check item by item, publish refusal naming item numbers and
  success after restoring, the detail key-set (the exact inverse of
  015's landing-payload test), Registry absence from both payloads,
  the statement appearing once claimable, stale-credit refusal plus the
  admin flag, the mode matrix for both routes, and both open-gate
  refusals. 015's router walk passes with its allowlist untouched.
- Docs: COMPLIANCE.md 8.01 row rewritten from deliberately-not-satisfied
  to satisfied-by-design; 8.01.2, 4.01, 8.01 items 8–11/8.01.1, and the
  004/005 8.01 rows updated. ROADMAP.md records 016 as built ahead of
  ship and drops the closed 4.01 improvement note.

**Standards touched**
- 8.01 — satisfied by design: every applicable item is a stored fact
  with a named payload field, a completeness check, and a publish gate;
  partial disclosure is impossible by construction.
- 8.01.1 — the registration/attendance policy is disclosed beside
  refund/cancellation and complaint resolution as published, versioned
  policies linked from the course page; unpublished policies now block
  publish as well as site-open.
- 8.01.2 — prerequisites and advance preparation must be a stored
  statement ("None" counts, blank does not) before a course can publish;
  precision of language remains the 008 reviewer's judgment.
- 4.01 — the "most recent publication, revision, or review date" is
  asserted on the detail payload by key-set test; the ROADMAP
  improvement note is closed.
- 7.01 — credit is displayed exactly as 005 stored it (rounded down to
  one-fifth); a stale credit refuses the whole course render rather than
  serving a number the formula no longer backs.

**Decisions**
- The publish gate includes items 8–10, superseding 011's "launch
  blocker, not a publish blocker" line: 016's rule that a course that
  cannot disclose completely cannot be published is the stronger and
  simpler invariant (docstring updated in `services/policies.py`).
- The payload refusal is exactly what the spec names — a stale credit.
  A fresh award below the minimum keeps 005's null-row rendering (it can
  no longer be published anyway; only pre-016 dev data can reach it).
- `sponsor_statement` is dropped from the serialized payload when
  inapplicable via a `model_serializer` on `CoursePublicDetail`, so
  every consumer of the model — route and audit bundle alike — gets the
  same key set.
- The test factory's publishable question list grew from 3 to 6
  questions: with the 2-second factory video, the question term
  (6 × 1.85 = 11.10 minutes) is what lifts the award to the 0.2 minimum,
  without which no API-built course could publish under the new gate.
  `make_published_course` now publishes the three policies itself.

**Known gaps**
- Frontend rendering was verified by build and by the payload tests; the
  by-eye browser pass of the catalog and disclosure pages through the
  hidden login, and the production deploy of 016, are the operator's
  steps.
- The published-but-incomplete flag lives on the admin course detail
  page only; the admin course list does not surface it.
- The open-gate refusal itemizes failing courses only when no published
  course passes; a failing course alongside a passing one is visible
  only on its own admin page (and is served publicly with null policy
  links — reachable only from pre-016 dev data).

## 017 — Self-registration and email verification
Shipped: 2026-08-31

**What changed**
- One email service (`backend/app/services/email.py`) with two backends
  chosen by `EMAIL_BACKEND`: `console` (dev and every test — message to
  the log, no network) and `smtp` (generic SMTP over STARTTLS from the
  five `EMAIL_*` env vars; provider-agnostic, the provider choice is an
  OPERATIONS.md decision). 019's certificates and 021's invitations will
  call the same `send`.
- Outbound log: `email_message` table (kind, recipient, subject,
  backend, created_at — never the body). Declared operational records,
  not CPE records, like 015's waiting list.
- `POST /api/v1/register` `{name, email, password, state?}`: creates an
  unverified `participant` account. State of licensure is optional,
  validated against `US_JURISDICTIONS` when present, stored in a new
  nullable `accounts.state` column. Email shape and the 002 password
  policy (`MIN_PASSWORD_LENGTH`) are reused verbatim from the auth
  service — no second policy.
- The constant response: every well-formed registration or resend
  answers the identical 200 (`CHECK_YOUR_EMAIL`, one shared constant in
  `services/registration.py`). Behind it: new email → account +
  verification email; existing active → already-registered email, no new
  row; deactivated → contact-the-sponsor email, no reactivation (9.02 —
  reactivation stays the deliberate 009 admin action). The taken-email
  branches hash the offered password anyway so response time matches the
  branch that stores one.
- Verification: `email_verification_tokens` — ≥256-bit random tokens
  stored as sha256 (fast hash on purpose; they are high-entropy, argon2
  is for passwords), 48-hour expiry (`VERIFICATION_TOKEN_*` constants),
  single-use, one live token per account (resend supersedes the prior).
  `POST /api/v1/verify` consumes the token and sets
  `accounts.email_verified_at`; expired/unknown/used/superseded tokens
  fail with one message. `POST /api/v1/resend-verification` follows the
  registration constant-response rule.
- Login: an unverified account is refused with the same 401 body as a
  wrong password (`authenticate` in `services/auth.py`). Admin/CLI
  account creation is unchanged: `create_account` marks those verified
  at creation (the hand-delivered initial password is the vouch), and
  the migration backfills all existing accounts the same way.
- 012 config validation learned the email settings: `EMAIL_*` is
  all-or-nothing, `EMAIL_FROM` must parse as an address, unknown
  `EMAIL_BACKEND` refuses boot; absent entirely is valid while
  coming-soon.
- Open gate: `launch_findings` gained the block finding
  `email_not_configured` — `coming_soon → open` refuses unless
  `EMAIL_BACKEND=smtp` with complete settings. Tests satisfy it with
  dummy SMTP config in the test env (conftest), never by weakening it.
- Admin: `POST /api/v1/admin/email/test` sends a test email to the
  requesting admin through the configured backend (502 with the SMTP
  error on failure); a Send-test-email button on `/admin/sponsor`.
  OPERATIONS.md gained the "Outbound email (017)" runbook section.
- Site mode: all three public routes sit behind
  `require_site_open_or_session` — 404 anonymously in `coming_soon`, the
  015 router walk stayed green with its allowlist untouched. Caddy rate
  limits register/verify/resend like login (10/min/IP).
- Frontend: `/register` (with the state dropdown and a link to the
  published registration policy — linked, not restated, per 8.01.1),
  `/verify`, `/resend-verification`, and a general "Didn't get your
  verification email?" link on the login page (a targeted hint would
  undo the login-door indistinguishability). The course page's reserved
  Registration section is untouched — enrollment is 018's.
- Tests: 313 passing (25 new) — byte-identical constant responses with
  the outbound log proving the branch, token lifecycle, login refusals,
  mode matrix, open-gate refusal/success, EMAIL_* config matrix, admin
  test email through both a working and a refusing backend.

**Standards touched**
- 8.01.1 — the registration form links the published
  registration/attendance policy; the flow cannot go live before the
  policy and the email machinery exist (open-gate findings).
- 9.02 — self-registered accounts inherit deactivate-never-delete
  unchanged; re-registration can never reactivate or duplicate a
  deactivated account. COMPLIANCE.md gained both rows.

**Decisions**
- The email backend is explicit config (`EMAIL_BACKEND`), not derived
  from whether `EMAIL_*` is set: the test env must satisfy the open gate
  with dummy SMTP settings while every actual test send stays on the
  console backend, which requires the two to vary independently.
- Verification links are built on `settings.cors_origins_list[0]` — in
  prod 012 already forces CORS_ORIGINS to exactly the production origin,
  so no new "site URL" variable was invented.
- The table is named `email_message` (singular), following the feature
  spec's naming verbatim over the plural house convention.
- Self-registration fits the existing 002 account model with no parallel
  table: two new nullable columns (`email_verified_at`, `state`), no
  change to roles. The migration backfills `email_verified_at =
  created_at` for existing accounts so admin/tester login behavior is
  untouched.
- Resend for an unknown address sends nothing (there is no one to
  write to) but answers the same constant 200.

**Known gaps**
- Password reset does not exist (002 never built it); recorded as the
  017a improvement note in ROADMAP.md. The token machinery was shaped
  for that reuse.
- The SMTP path is exercised in tests only as far as a refused
  connection; a real provider send is the operator's step 3 in the new
  OPERATIONS.md section, before the open flip.
- No self-service email-address change; that remains an admin action.
- The 015 browser-check date correction was conditional on Dane
  reporting one; none was reported, so no correction entry.

## 018 — Stripe checkout
Shipped: 2026-08-31

**What changed**
- Payments: one `payments` row per checkout attempt that reached Stripe
  (session id unique, amount/currency as Stripe reported them,
  `pending → paid → refunded` plus `expired`), plus
  `stripe_webhook_events` for idempotency. Financial records, never
  deleted, outliving `RETENTION_YEARS`. Migration `a9d21c5b7e30`.
- Boundary: `services/stripe_gateway.py` owns every Stripe API call and
  the webhook signature check, on the official `stripe` package (new
  dependency, justified in requirements.txt). Checkout is Stripe's
  hosted page — card data never transits superCPE. Tests stub this
  module; nothing in the suite touches the network.
- Price: admin-set integer cents on the course (`PUT
  /admin/courses/{code}/price`, editable while published — a business
  fact, not content, so no `touch`). Publish now also requires a price
  (> 0), as the `price_missing` readiness block finding, worded as a
  business rule and listed apart from the 8.01 disclosure items; it is
  in `PUBLISH_ONLY_CODES` so assessment previews are unaffected. Price
  renders as dollars on the catalog card and course page.
- Checkout: `POST /api/v1/checkout` for a logged-in (hence 017-verified)
  participant — refusals for unpublished course and
  already-actively-enrolled; re-purchase after expiry allowed; a live
  `pending` session younger than `CHECKOUT_SESSION_LIFETIME_HOURS` is
  returned, not duplicated. The payment row is written `pending` before
  the redirect URL is returned; metadata carries account id, course
  code, payment row id. Stripe sends the receipt email; superCPE sends
  no payment email of its own.
- Webhook: `POST /api/v1/stripe/webhook`, signature-verified, refuses
  anything unsigned (400); idempotent by stored event id.
  `checkout.session.completed` marks the payment paid and creates the
  enrollment via 010's one constructor (`source="purchase"`, one-year
  clock) in one transaction; `charge.refunded` marks the payment and
  deliberately stops; `checkout.session.expired` marks abandoned
  sessions; unhandled types answer 200 and are logged by name. A missing
  payment row logs loudly and answers 200 — Stripe retries 500s forever.
- Void: enrollments gained `voided_at`/`voided_by_account_id`
  (deactivate-never-delete); derived status gained `voided` (checked
  after completed, before expired). `POST
  /admin/enrollments/{id}/void` is the guarded, logged "access ends"
  answer to a refund; it refuses non-active enrollments — a completion
  is an immutable 9.02 record no refund can unmake. Voided enrollments
  refuse the player/progress/review routes (403) and the assessment via
  the existing active-only rule.
- Success page: `/purchase/success` polls
  `GET /api/v1/checkout/{session_id}/status` (owner-only, 404 for
  anyone else) until the webhook lands, then links the course; after
  ~30s an honest "taking longer than usual" state names the sponsor's
  contact address.
- Course page: the reserved Registration section is live — price and
  Enroll (redirect to Stripe) for a participant, sign-in/register links
  for visitors, "you're enrolled" with a player link when enrolled.
- Admin: `/admin/payments` — the paper trail with Stripe dashboard
  links, the loud refunded-with-active-enrollment flag, and the Void
  action (confirm dialog; the flag clears once answered).
- Config and gate: `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` /
  `STRIPE_WEBHOOK_SECRET` join 012's validation, all-or-nothing, absent
  entirely valid while coming-soon; the open gate gained the
  `payments_not_configured` block finding. Test env satisfies it with
  dummy keys in conftest. OPERATIONS.md gained "Payments (018)":
  account setup, restricted key, webhook registration, Stripe CLI
  test-mode walkthrough, and the refund runbook.
- Site mode: all three 018 public routes sit behind
  `require_site_open_or_session` — 404 anonymously in `coming_soon`;
  the 015 router walk stayed green with its allowlist untouched.
- Tests: 332 passing (19 new) — checkout refusal matrix, pending-session
  reuse, exactly-one-enrollment across webhook replays and duplicate
  events, unsigned webhook refused, refund-leaves-enrollment-intact plus
  flag and void, orphaned-metadata tolerance, owner-only status, price
  business-rule publish refusal, open-gate refusal/success on Stripe
  config, boot all-or-nothing, 018 mode matrix.

**Standards touched**
- 8.01 item 9 — courses are now actually "sold for a fee"; the refund
  policy link on the point-of-sale page is load-bearing, and the refund
  workflow stops where the policy begins (webhook marks, admin decides).
  COMPLIANCE.md row updated.
- 9.02.2(3) — the enrollment the webhook creates carries the one-year
  expiration from 010 unchanged ("date of purchase or enrollment").
- 9.02 — payment amounts are recorded per charge as Stripe reported
  them, never re-derived from the course's current price. Deliberately
  beyond the letter: 9.02.2's element list names no payment records;
  COMPLIANCE.md row added saying exactly that.

**Decisions**
- The webhook is the sole creator of enrollments; the success page only
  polls. A browser return proves nothing.
- The enrollment a payment created is derived (account + course +
  source + enrolled-after), never stored as an FK — house
  derived-state rule, and it keeps the paid+enrolled write a single
  transaction through 010's constructor unmodified.
- Refunds never unwind access automatically; the void action is the
  admin's policy answer, and completed enrollments cannot be voided.
- Voided enrollments lose the player too (unlike expired, which keeps
  read access): the money came back, the access ends.
- Price edits are allowed on published courses without `touch`: price is
  a business fact, not content — no re-review, no credit staleness, and
  not retroactive by design.
- Table names follow the plural house convention (`payments`,
  `stripe_webhook_events`).

**Known gaps**
- Sales tax, coupons, subscriptions, multiple currencies, invoicing,
  and self-service refunds are out of scope; Stripe Tax recorded as a
  ROADMAP improvement note.
- Certificate email on completion is 019; paying starts the clock and
  nothing else.
- Disputes (`charge.dispute.*`) are logged as unhandled, not mapped to
  `refunded`; if disputes ever occur, handling them is a small follow-up.
- The operator walkthrough (Stripe account, webhook registration,
  test-mode end-to-end with the Stripe CLI) is written in OPERATIONS.md
  but not yet performed — acceptance 7 is the operator's, later, not
  build-blocking.
- The 015 browser-check date correction was conditional on Dane
  reporting one when feeding this spec; none was reported, so no
  correction entry.

## 019 — Certificate delivery and public verification
Shipped: 2026-08-31

**What changed**
- On completion, the participant now receives one email (kind
  `certificate`) with the certificate PDF attached, a sentence naming
  the course, credit, and completion date, and a link to their
  certificates page — sent strictly after the completion transaction
  commits (`app/services/delivery.py`, hooked into the passing submit
  route). Delivery failure cannot fail completion: the outcome lands in
  `delivery_status` (`pending`/`sent`/`failed`) and `delivered_at` on
  `completions` (migration `b6e2d94c8a17`, CHECKs hand-written).
- 017's email service gained its one planned extension: an optional
  attachment on `send`, carried by both backends;
  `email_message.attachment_filename` logs the filename, never the
  bytes or the body.
- Admin: `POST /api/v1/admin/completions/{id}/resend` (guarded, logged
  like every send, updates delivery status; renders first if needed),
  a Delivery column with a loud `delivery failed` badge and a Resend
  button on the course page's Completions table. No retry machinery.
- Public verification: `GET /api/v1/certificates/verify/{code}` answers
  from the certificate snapshot only — participant, course, field of
  study, credit, completion date, sponsor, "Self study" — so later
  course edits can never move it. Unknown and malformed codes answer
  one identical 404 (the site gate's own shape); the route is public at
  `open`, 404 anonymously in `coming_soon`, and the 015 router walk's
  allowlist is unchanged. Caddy rate-limits the lookup like the signup
  routes (asserted by test).
- Frontend: `/certificates/verify` (code-entry box) and
  `/certificates/verify/{code}` (shareable result card) — the namespace
  deliberately avoids 017's `/verify`, and a test pins both API
  namespaces resolving independently. The participant's completion
  panel now shows the verification code with copy-code / copy-link
  affordances.
- The rendered PDF's verify line now reads "Verify this certificate at
  supercpe.com/certificates/verify — code: …" (it previously pointed
  at `/verify/{token}`, a URL inside 017's email-verification
  namespace that never had a resolver).
- No verification-code backfill was needed: `verification_token`
  (256-bit, unique, indexed) has been on every completion since 010 and
  is the printed code. Existing dev-only certificates verify by their
  codes with their PDFs untouched — snapshots and stored PDFs are
  immutable, and production starts empty, so no real certificate will
  ever lack the printed line.
- COMPLIANCE.md: 9.01 row added (documentation delivered immediately by
  email and on demand, well inside 60 days) and 9.01.1 row added (the
  verification page as the sponsor's channel for standing behind the
  documentation it issues). ROADMAP marks 019 built ahead of ship;
  OPERATIONS.md gained "Certificate delivery (019)".

**Standards touched**
- 9.01 — the ≤60-day timeliness expectation is now met without being
  asked: email at completion, download on demand unchanged.
- 9.01.1 — the sponsor issuing and standing behind the certificate
  gains a public confirmation channel serving the frozen snapshot.

**Decisions**
- The existing `verification_token` is the verification code — it
  already met every requirement (≥128 bits, URL-safe, unique, plain,
  indexed, minted at issuance), so no new column and no backfill.
- The send is synchronous in the submit route after
  `assessment.submit`'s own commit, not a FastAPI background task:
  yield-dependency teardown runs before background tasks (the session
  would be gone), and a caught exception plus a status write is the
  whole requirement.
- A render blocked by sponsor issuance fields leaves delivery
  `pending`, not `failed` — nothing failed; there is nothing to send
  yet. Resend renders-then-sends once the fields are filled.
- The verification response mirrors the certificate's own participant
  line (display name, or email when blank) — the page confirms what
  the paper says, nothing more.
- Resend works from any status (it is also the "send now" for pending
  completions rendered late).

**Known gaps**
- Dev-era certificate PDFs print the old `/verify/{token}` URL, which
  resolves to 017's email-verification page, not the certificate page;
  their codes verify at `/certificates/verify` regardless. Accepted:
  re-rendering would violate snapshot immutability, and production
  starts empty.
- No automatic delivery retries, per spec — flag plus human button;
  retries become a follow-up only if reality demands them.
- Revocation remains deliberately unbuilt; every code that ever
  verified keeps verifying.

## 020 — Per-jurisdiction credit policy
Shipped: 2026-08-31

**What changed**
- `jurisdiction_policies` table (migration `c4d7e81f2a90`): one
  admin-maintained row per `US_JURISDICTIONS` code — credit increment
  (`one_fifth`/`one_half`/`whole`/`unknown`), quoted non-technical cap
  note, source, verification date, admin-only notes. Ships empty;
  create-on-edit, no seeded increments ever. Displayable (increment
  known + source + date) and the 12-month re-verify nudge are derived
  live, never stored.
- `/admin/jurisdictions` (API and page): all 55 codes with inline edit
  of the five fields, a Displayable column, and the staleness nudge.
  Guarded by 009's admin walk automatically.
- Participants set/change/clear their own state of licensure on a new
  `/account` page (`GET`/`PUT /auth/me/state`, validated against
  `US_JURISDICTIONS`) — their claim, no verification step. 017's
  registration flow and admin surfaces untouched.
- `GET /courses/{code}/jurisdiction-note`: the per-viewer hint — the
  verified increment; when coarser than one-fifth, the recommended
  credit rounded **down** to it (7.01.1's arithmetic, computed per
  request, labeled computed, never stored); the cap note only when the
  course's field is non-technical per the 2024 Fields of Study
  classification already transcribed in `constants/fields_of_study.py`
  (this feature wires the flag's first reader); the verification date;
  and a fixed final-authority sentence. Every miss — anonymous, no
  state, unverified row, unknown field, unrenderable course — is the
  same 404: absence, not a stub.
- Course page renders a "For your board (XX)" panel with exactly that
  response; the final-authority sentence renders whole. 016's public
  payload and key-set test byte-for-byte untouched (separate endpoint
  on purpose: the hint is per-viewer, the payload is cacheable).
- Certificate render pinned jurisdiction-free by test; 005's stored
  credit asserted unchanged by the round-down.
- Constants in `constants/jurisdiction_policy.py` (7.01's three
  increments as Decimal steps, the 12-month cadence, the sentence).
- OPERATIONS.md "Jurisdiction policies (020)"; COMPLIANCE.md gained a
  7.01/7.01.1 update row; ROADMAP marks 020 built ahead of ship.
- 364 tests (24 new).

**Standards touched**
- 7.01 — board increment differences are now surfaced per verified
  jurisdiction to the claiming CPA, who keeps the Standard's own duty
  to check; awards stay one-fifth (005 unchanged).
- 7.01.1 — the round-down-to-coarser-increment arithmetic, computed
  per request for display only.

**Decisions**
- The hint answers 404 for every miss (including anonymous, via a new
  `optional_account` dependency) rather than 401 — whether a hint
  exists for somebody is nobody else's business, matching /my's 404
  posture.
- `/auth/me/state` is its own GET/PUT pair; `MeOut` and its exact-key
  test stay untouched.
- Caps are quoted text per reporting period, never computed —
  superCPE cannot know a CPA's other CPE and must not pretend to.
- `field_of_study` was already constrained to the NASBA list at
  package ingest (002's CHECK + validation), so no course-side
  validation or readiness flag was needed; the technical flag's lookup
  is `FIELDS_OF_STUDY.get`, and an unknown/legacy value yields no hint.
- A one-fifth board shows the stored credit with no computed value at
  all — there is nothing to compute.
- The fields-of-study technical/non-technical mapping is transcribed
  from `docs/2024-Fields-of-Study.pdf` (January 2024), done in 002;
  this feature is its first reader.

**Known gaps**
- The table ships empty and stays empty until Dane verifies rows;
  until then the feature is invisible everywhere (by design, but worth
  saying: deploying this changes nothing participants see).
- Reporting-period cap arithmetic is deliberately out of scope —
  superCPE cannot know a participant's other CPE.
- Deploy is the operator's: run the migration, reload; no new env
  vars, no Caddy change.

## 021 — Waiting-list invitations
Shipped: 2026-08-31

**What changed**
- `invited_at` and `invitation_status` (`sent`/`failed`, both nullable,
  CHECK-paired) on `waiting_list`, with migration `e2c94b6a1d73`. An
  entry is invitable while active and never successfully invited; the
  rows remain not CPE records (docstring unchanged).
- `app/services/invitations.py`: the one promised email per entry.
  `send_all` refuses while `site_mode` is `coming_soon` (the links
  would 404; the flip stays rehearsable with no mass email riding on
  it), then sends sequentially through the 017 service (kind
  `invitation`) with a per-row commit — the message row and the `sent`
  flag land in one commit, a refused send is recorded as `failed` and
  never stops the run. Re-running skips every `sent` row, so the batch
  button is its own retry; `resend` is the per-row recovery, 019-style.
  The flip itself never sends — the button is deliberately separate.
- `POST /api/v1/admin/waiting-list/invitations` (run + summary:
  attempted/sent/failed/skipped) and
  `POST /api/v1/admin/waiting-list/{id}/resend`; the admin listing
  gained invitation counts and per-row status; the CSV export gained
  `invited_at` and `invitation_status`.
- The email: superCPE is open, one sentence naming the course, a link
  to the course page (where the full 8.01 disclosure lives) and to
  /register, and the closing line keeping 015's promise — told once,
  never emailed again. No credit figure, field of study, level, price,
  or "National Registry" (pinned absent by test). No unsubscribe
  machinery: there is no subscription.
- `/admin/waiting-list` gained the Invitations panel: counts (active /
  invited / failed / invitable), Send behind a confirm dialog repeating
  the refusal rule and the count, an invitation column, per-row Resend
  on failed rows.
- OPERATIONS.md gained "Waiting-list invitations (021)" and the
  "Opening day (021)" ordered checklist (014 → policies → email →
  Stripe → jurisdictions → gate → flip → smoke test → **then** Send
  invitations → watch the failed column), cross-referencing each
  feature's own section.
- ROADMAP marks 021 built ahead of ship and **Phase C code complete**:
  what remains is 014 on production, the Registry application, and the
  flip.
- 371 tests (7 new).

**Standards touched**
- 8.01 — COMPLIANCE.md gained an update row on the 015/016 8.01 row:
  the invitation follows the landing page's rule (link, don't restate)
  now that full disclosure exists to link to; it carries no descriptive
  material and no Registry words.

**Decisions**
- Idempotence is structural, not machinery: `sent` rows are skipped by
  every later run, so partial-failure recovery is pressing the same
  button again; no retry daemon exists.
- The row status is staged before the send so 017's own commit records
  the `email_message` row and the `sent` flag atomically — a crash
  between send and record cannot leave a delivered email unrecorded.
- The send also refuses (beyond the coming_soon rule) if no course is
  published — there would be no course page to link. The open gate makes
  this unreachable in practice; the refusal keeps the email honest if
  everything were unpublished after the flip.
- The named course is the published catalog's first (production has
  exactly one); the sentence uses the stored title, no other fact.
- Per-row Resend refuses a `sent` row ("one email, ever") and a removed
  row; it exists for symmetry with 019, but the batch re-run is the
  expected path.
- The 015 CSV and listing key-set tests were extended for the two new
  columns rather than frozen — the 015 promise they protect (removed
  rows leave every export) is unchanged and still asserted.

**Known gaps**
- Deploy is the operator's: run the migration, reload; no new env vars,
  no Caddy change. The feature is invisible until opening day — the
  send refuses in `coming_soon`, which production is in.
- Phase C code is complete, but launch still waits on 014 (production
  ingest + real reviewer sign-off), the Registry application, and the
  flip itself, per "Opening day (021)".

## 022 — Site identity and link previews
Shipped: 2026-08-31

**What changed**
- supercpe.com now looks like itself everywhere a link lands: a real
  favicon (SVG, hashed by the build, with a 32px `favicon.ico`
  fallback), `apple-touch-icon.png`, 192/512 manifest icons, a
  `site.webmanifest`, and a 1200×630 `og.png` link-preview card. The
  mark is a deliberately plain "sC" monogram drawn as code in the site's
  own palette — every asset regenerates from one committed script
  (`frontend/scripts/generate_identity.py`, Pillow on the backend venv,
  the certificate DejaVu fonts) reading the palette from `global.css`
  and the words from `site.config.json`.
- `frontend/index.html` carries the full static metadata set: title,
  description, canonical, theme-color, `og:type/site_name/title/
  description/url/image` (absolute https URL — scrapers resolve
  nothing), `twitter:card=summary_large_image`, and a minimal JSON-LD
  Organization block (name, url, logo — nothing it can't back). The
  tags are static and site-wide because scrapers run no JavaScript
  against a SPA; per-course OG cards would need SSR and are a ROADMAP
  improvement note, not built.
- One source for the words: `frontend/site.config.json` holds the
  origin, name, tagline, and description. A ten-line inline Vite plugin
  (`siteMeta` in `vite.config.js`) fills index.html's SITE_ tokens from
  it (and the theme color from `global.css`); the OG-image script and
  the page-title helper read the same file, so the three cannot drift.
- Per-route tab titles: `usePageTitle` (frontend hook, no dependency)
  on every public and participant page — the course page uses the
  loaded course title, the unmatched route says "Page not found" only
  when the 404 actually renders (while `coming_soon`, SiteGate shows
  the landing page and the tab keeps the site-wide title). Admin and
  review pages unchanged.
- `robots.txt` (static, `frontend/public/`): allow all, `Disallow:
  /admin`, and the Sitemap line — the coming-soon page is meant to be
  indexed, so the domain has standing by opening day.
- `GET /api/v1/sitemap.xml`, mode-aware: only the root while
  `coming_soon`; at `open` the root, `/courses`, each renderable
  published course page (the catalog's own filter — a stale credit is
  never announced), `/policies`, `/certificates/verify`, and
  `/register`. Added to `INTENTIONALLY_PUBLIC` marked 022 — the
  designed mechanism for a deliberately anonymous route; the router
  walk holds everyone else to 401/404 as before. Caddy routes it with a
  dedicated `handle /sitemap.xml` block that rewrites to
  `/api/v1/sitemap.xml` and proxies to the API (no rate limit — a GET
  as cheap as any the SPA serves).
- The 021 invitation's `_site_origin` helper moved to the site service
  as `site_origin()` so the sitemap and the invitation read the same
  origin (prod: CORS_ORIGINS, exactly https://supercpe.com).
- OPERATIONS.md "Site identity (022)": how to regenerate after a
  rebrand, why link-preview and favicon caches lag a deploy (time and a
  query-string variant are the only levers), and the Caddy-reload note.
- 379 tests (8 new in `test_identity.py`): the content rules on the
  rendered index.html (no "National Registry", no "QAS", no credit
  figure, no price), the full tag set with absolute `og:image`, valid
  minimal JSON-LD, every Vite default gone, manifest and robots.txt
  pinned, and the sitemap mode matrix (coming_soon vs open,
  published-courses-only).

**Standards touched**
- 8.01 — COMPLIANCE.md gained an update row on the 015/016 8.01 row:
  the site-wide metadata follows the landing page's and the
  invitation's rule (link, don't restate) — the description describes
  the sponsor, not the course, pinned by test; the sitemap never
  announces a page that cannot disclose completely.

**Decisions**
- "superCPE — Self-Study CPE for CPAs" is the one line used everywhere
  (tab, OG card, og.png); the description claims only that the platform
  is built to the NASBA Standards — a statement about design, not a
  Registry claim. Dane has final word: both live in `site.config.json`,
  and a change there plus one script run is the whole edit.
- The sitemap is served by the backend, not a static file, because its
  contents depend on `site_mode` and the published catalog — derived
  state, computed where it lives (the site service), never stored.
- No analytics, no third-party scripts, no tracking pixels — 015's
  decision stands; this feature is metadata only.
- `og.png`, `favicon.ico`, `apple-touch-icon.png`, and the manifest
  icons keep fixed names in `public/` (scrapers and old browsers fetch
  them blindly; the OG URL is baked into a static tag); only the SVG
  favicon rides the hashed asset pipeline. Stale-cache recovery after a
  rebrand is time, by design.

**Known gaps**
- Deploy is the operator's: routine deploy (frontend rebuild picks up
  `public/` and the tags) plus a Caddy reload for the `/sitemap.xml`
  handle; no migration, no new env vars. The by-eye step — texting the
  production URL and seeing the card — waits for that deploy, and
  preview caches may lag it (OPERATIONS.md says so).
- Per-course OG cards need SSR or edge injection; recorded as a ROADMAP
  improvement note, deliberately not built.
