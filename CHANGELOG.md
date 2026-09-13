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

## 023 — Text-first course packages
Shipped: 2026-09-01

Part B of a three-part feature. Part A (the contract change in
`docs/course-package.md`) shipped with it and must be mirrored into
video-tool identically; Part C (authoring and export) is video-tool's own
session and is not built here. Everything below was built against the
hand-made fixture package the spec called for, which is now
`backend/tests/factories/text_package.py`.

The strategy this serves is recorded in
`docs/decisions/2026-09-01-text-first.md` and ROADMAP Phase D, not here.

**What changed**

*The contract (Part A)*
- `manifest.json` gains `"kind": "video" | "text"`. **Absent means
  video**, so every package exported before today is still valid and
  ingests through byte-identically the same code path and the same
  refusal messages.
- A text package is `manifest.json` + `guide/*.md` + optional `media/*` +
  `questions.json`. Sections carry a `role`
  (`front_matter`/`body`/`glossary`/`appendix`); review questions carry
  `after_section` where a video package's carry `after_block`; media
  carry `placement.after_section` and must claim
  `av_is_additional_learning: true`; `glossary_terms` carry the key terms.
- `word_count` is **not a manifest field for a text package** and is
  refused if present. `content_hash` is defined for the new layout
  (sections in manifest order, then questions.json, then media in
  manifest order). The 7.02.5 exclusion list and the 7.02.7 test are
  quoted verbatim in the contract, and it ships the "How this course
  works" front-matter template 4.05.3 item 4 requires.

*Ingestion (B1)*
- `validate` peeks the manifest's `kind` before choosing layout rules and
  dispatches to `_validate_video` (the existing body, unchanged) or
  `_validate_text`. A manifest that is missing or unparseable peeks as
  video, so a broken package still gets the refusals it always got.
- Word counting is superCPE's, from the shipped markdown
  (`backend/app/services/word_count.py`): fences, HTML, images, and link
  URLs stripped; headings, link text, and inline code kept; a token counts
  as a word if it holds a letter or digit. The rules are written out in
  the contract so an author can hand-count a section and get the same
  number, and a test hand-counts one (3 + 29 + 22 + 10 = 64).
- Three new tables — `package_sections`, `package_media`,
  `glossary_terms` — normalized in the same transaction as the package
  row, like the questions. `lesson_packages` gains `kind` and
  `word_count_source`; `video_key`, `transcript`, and `measured_at`
  become nullable under paired CHECKs that make each present exactly when
  the kind is video. `questions` gains `after_section`, and the
  "after_block iff review" CHECK becomes "exactly one placement iff
  review".
- Ingestion warns rather than refuses on an empty glossary (the publish
  gate refuses); `IngestResponse` carries the warnings.
- The package detail view gained a human summary above the raw manifest
  — kind, words counted vs shipped, sections by role with counted/
  excluded, media with durations, question counts, glossary size. This is
  the walkthrough finding that `word_count` was visible only inside raw
  JSON.

*Credit (B2)*
- A text lesson feeds **both** the word term and the A/V term; a video
  lesson still feeds one or the other. `CreditLessonRow` gained `kind`
  and `word_count_source`, both defaulted so a breakdown stored before
  today rebuilds through `from_stored` unchanged.
- The retained record now names each lesson's basis: `words: N counted
  (computed from package text, body sections only, 7.02.5)` or `(from
  manifest, trusted)`; A/V as `(supplemental, additional learning)`,
  `(program is the video, 7.02.7)`, or `(N s narrates the text)`. The
  middle one is the label fix — an all-video lesson used to print
  "(additional learning)".

*The reader (B3)*
- `GET /my/enrollments/{id}/lessons/{pid}/read`, plus an ungated
  admin/reviewer preview at `GET /courses/{code}/lessons/{pid}/read`.
- **The gate is server-side and withholds the text.** A body section
  whose preceding section still has an unanswered review question comes
  back with `markdown: null`, and so do its media and its own questions.
  Front matter, glossary, and appendix are never gated.
- No answer key in the payload, the 006 rule verbatim, with the
  equivalent test. No seek lock on supplemental clips.

*Search and glossary (B4, B5)*
- `GET /my/enrollments/{id}/search?q=` and
  `GET /my/enrollments/{id}/glossary[?term=]`, each with an admin preview
  twin. Search reads `package_sections` and nothing else.
- `/how-it-works` (4.05.3 item 4, site-wide) rewritten to describe both
  formats, including that a study guide's videos add to the text rather
  than reading it aloud.

*Review scope and the publish gate (B6, B7)*
- The 4.02 sign-off form now shows what an approval asserts, versioned in
  `backend/app/constants/review_attestation.py`; a course with text
  lessons adds the 7.02.7 and 7.02.5 lines. No schema change, per spec.
- Three accumulating block findings for a course with any text lesson:
  `text_word_count_zero`, `glossary_missing` (4.05.3 item 3),
  `front_matter_missing` (4.05.3 item 4). All three are in
  `PUBLISH_ONLY_CODES`: they gate publish, not the assessment preview.

*Elsewhere*
- The audit bundle writes a text package's sections as shipped plus a
  `word-count.txt` showing the 7.02.5 accounting section by section, and
  media by reference — it would otherwise have crashed on a package with
  no transcript.
- Frontend: a `Reader` component (contents, gated sections, inline clips,
  in-place review questions, search box, glossary panel), mounted by
  `MyLesson` and the admin/reviewer preview beside the existing `Player`;
  the package overview on the admin package view; the attestation above
  the review form; kind-aware lesson and credit rows on the admin course
  page.

**Standards touched**
- 7.02.5 — **the 005 trust gap closes for text packages.** superCPE
  counts the words itself from the shipped body sections, and the
  paragraph's exclusion list is a `role` with a CHECK constraint behind
  it rather than an author's promise. COMPLIANCE.md carries the update
  row; the 005 row stands unchanged for video packages.
- 7.02.7 — a text package's clips are additional-learning by
  construction: the contract requires the claim per item, ingestion
  refuses without it quoting the paragraph's own test, and a CHECK on
  `package_media` means a row that does not claim it cannot be stored.
- 7.02.6 — same arithmetic, a third shape of input, and a record that
  names each lesson's basis in words.
- 4.05.3 items 2 and 3 — **built, and publish-gated.** The 011 row's
  "not built" gap closes for text lessons.
- 4.05.3 item 4 — the front-matter block is required content and its
  absence blocks publish; `/how-it-works` covers both formats.
- 5.01.2.1 — the same "throughout the program in sufficient intervals"
  requirement, expressed as section gates instead of video pauses.
- 4.02 — the reviewer is now shown what they are asserting.

**Decisions**
- **4.05.3 item 1 (overview of topics) is answered by the course
  description**, not by a required section titled "overview". The
  `description_missing` publish gate already existed and applies to every
  course of either kind; adding a second, text-only overview rule would
  have made the same requirement answerable two different ways depending
  on the format. The per-lesson objectives outline on the course page
  (011) continues to serve it alongside the description.
- **No forward-seek lock on supplemental clips**, closing the ROADMAP
  open question. Completion is verified by the qualified assessment
  (6.01.2); interval placement is satisfied by the section gates
  (5.01.2.1); the seek lock was always a sponsor design choice, not a
  Standards requirement. The video-only player keeps its lock — changing
  that is its own decision. Recorded in the decision doc too.
- **Every review question placed after a section gates the next one**,
  not just the last. A section may carry more than one, and keying them
  by section (the first implementation) let a participant open the next
  section by answering whichever happened to come last. Caught by running
  the fixture through a real server; the test now answers them in the
  wrong order first.
- A locked section's markdown is **absent from the payload**, not hidden
  by the browser. A gate the client could skip is not a gate.
- Text packages keep `course_code`, `position`, `sources`, `author`, and
  `content_hash` with the same meanings and rules as video packages. The
  spec's example manifest elides them; the system needs them to attach a
  lesson, refuse an uncited one, satisfy 9.02.2(4), and version a
  re-upload. The contract now says so explicitly.
- `duration_seconds` on a text package is the sum of its clips, so the
  column means the same thing for both kinds: this lesson's actual
  audio/video duration time. Durations are ffprobe-measured and truncated
  down to whole seconds — a term may understate, never overstate.
- Per-section word counts store each section's real size, including
  excluded ones, rather than zeroing the excluded. The difference between
  "shipped" and "counted" is exactly what 7.02.5 removed, and a reviewer
  should be able to see how large the appendix was.
- The attestation text is versioned, not stored per review — the spec's
  call ("no schema change"). Storing the signed text on `course_reviews`
  would be better evidence; see the known gap.
- The 016-date correction the spec asks about was already carried by
  017's entry (and again by 018's): it was conditional on Dane reporting
  a browser-check date, none was reported, and no correction entry was
  owed. Nothing further is carried here.

**Known gaps**
- **Part C is not built.** video-tool cannot yet export a text package;
  `docs/course-package.md` must be copied into that repo identically, and
  the export-time word-count preview, the `after_section` placement, and
  the `av_is_additional_learning` export refusal are that session's work.
  Until then the only text package that exists is the test fixture.
- **The contract is mirrored in one repo only** (acceptance 10 is half
  done). Copying `docs/course-package.md` into video-tool is a Part C
  step and cannot be done from here.
- Acceptance 9 (the operator run on production) was **performed locally,
  not on production**: the fixture was ingested through a real uvicorn
  against the dev Postgres, the package summary and the credit record
  wording were read off the live API, and the draft course and its
  package were deleted (which exercised the new media-object cleanup).
  The production run is the operator's, after deploy. The migration
  round-trips up and down; there is no data migration, because every
  existing row is a video package and the server defaults say so.
- The attestation is not stored with the review it belongs to, so a
  future reader infers the wording from `ATTESTATION_VERSION` and the
  sign-off date rather than reading it on the row. Worth its own small
  feature.
- Search is plain case-insensitive substring matching over stripped
  prose. No stemming, no ranking, no multi-term scoring — 4.05.3's own
  example is "an index or key word search function", and this is that.
  A large catalog may want more.
- A text lesson still has a `lesson_progress` row shape built for video
  (`furthest_seconds`), which for a study guide is meaningless; the
  participant course page shows "Study guide" instead of a timecode, and
  nothing reads the number. Removing it would touch the 010 progress
  contract and was left alone.
- `ASC842-PCX` is not migrated and was not touched (explicitly out of
  scope). No pricing changes.
- Deploy is the operator's: one Alembic migration, no new env vars, no
  new storage prefixes (media lands under the existing `packages/`, which
  013's backup policy already covers).

## 023a — manifest.json joins the content hash

Shipped: 2026-09-01

**What changed**
- `content_hash` now covers `manifest.json` first, for both package
  kinds, then the sequence each kind already defined: video —
  transcript.md, questions.json, video.mp4; text — the section files in
  manifest order, questions.json, the media files in manifest order.
  `manifest_hash_bytes` in `backend/app/services/packages.py` is the new
  first ingredient of both digests.
- The manifest is hashed **without its `content_hash` key** — the digest
  cannot cover its own field — and over a **canonical serialization of
  the parsed object** (`sort_keys=True`, `separators=(",", ":")`,
  `ensure_ascii=False`, UTF-8), not the file's literal bytes. The literal
  bytes are unusable here: the exporter has to know the digest before it
  can finish writing the file, so the only form both repos can arrive at
  is one that ignores the written file's indentation and key order. Both
  properties are stated in `docs/course-package.md` under "The canonical
  manifest bytes" and implemented identically by the test factories.
- `docs/course-package.md`: one definition sentence rewritten per kind
  plus the new shared section; the text kind points at it rather than
  restating it, and names the case that makes it vivid (an
  `appendix` → `body` role flip moves the credit with every file in the
  zip byte-identical).
- The two refusal messages now name manifest.json in the byte order they
  report; rule numbers and everything else about them are unchanged.
- `backend/tests/test_manifest_hash.py`: the feature's acceptance
  criteria — a byte-identical re-upload of each kind is still a no-op; a
  text role flip alone is a new version whose computed word count moved
  by exactly the appendix's words (with a second test proving the two
  zips differ in nothing but that one manifest word); a video
  `word_count` change alone is a new version that moves a holding
  course's stored credit; and the canonical bytes behave as the contract
  says.

**Standards touched**
- 7.02.6 — the formula is untouched; its inputs are now inside the
  identity of a package version, so a re-export that changes only
  `word_count`, a section `role`, or `av_is_additional_learning` can no
  longer be deduplicated away with the credit left standing on the old
  number. COMPLIANCE.md carries the update row.
- 7.02.5 — a section `role` decides whether its words are counted at all;
  that decision now moves the hash.
- 7.02.7 — `av_is_additional_learning` likewise.
- 9.02.1(8) — what makes a retained package version distinct from its
  predecessor now includes its descriptive record, not only its files.

**Decisions**
- **Canonical serialization, not raw manifest bytes.** current-feature.md
  says "the raw bytes of `manifest.json`", and its own chicken-and-egg
  guard rules that out: the exporter must remove `content_hash` to hash,
  which means it is hashing something other than the file it eventually
  writes. Raw-byte agreement would then depend on the exporter and the
  ingester reproducing each other's whitespace and key order exactly.
  Canonical bytes over the parsed object make the two agree by
  construction, and cost the contract three lines to specify. This is the
  one place the implementation departs from the spec's literal wording,
  and the departure is what the spec's own guard requires.
- Stored rows keep their historical hashes. They were computed under the
  definition of their day and remain valid records of what was ingested;
  nothing is re-hashed retroactively.
- **Consequence, as the spec asks it be recorded:** the first re-upload
  of a byte-identical pre-023a package after this deploys hashes
  differently and creates version N+1 once. Harmless — a new version of
  identical content — and on the current disposable database, invisible.
- The walkthrough's message-accuracy finding is **resolved by
  construction, not by rewording**. "Already ingested — nothing was
  created. Lesson X vN is unchanged" was false when the manifest sat
  outside the hash; with it inside, a hash match means the package really
  is unchanged, so the frontend string in
  `frontend/src/pages/AdminPackages/AdminPackages.jsx` is left exactly as
  it is.
- No schema change and no migration: `lesson_packages.content_hash` is
  the same column holding the same kind of value.
- A stale comment in `backend/tests/test_courses.py` ("the content hash
  ignores the manifest") was corrected rather than left to mislead. The
  per-version distinct transcripts it explains are now redundant but
  harmless, and were not churned.

**Known gaps**
- **Mirroring into video-tool is not done** and is out of scope by the
  spec: copying `docs/course-package.md` into that repo is the first step
  of video-tool 05, which is why this feature ran first. Until then no
  exporter implements the new definition — only the fixture factories
  here do, which is what the tests exercise.
- The 005 gap stands: a video package's `word_count` is still trusted
  from the manifest. 023a only guarantees that a corrected number is
  ingested rather than discarded. Text packages remain the format where
  the count is computed (023).
- No retro-rehashing of stored packages, by the spec's instruction. A
  reader comparing an old row's hash against the current definition will
  not be able to reproduce it; the definition it was computed under is in
  this changelog and in COMPLIANCE.md.
- Deploy is the operator's: no migration, no new env vars, no new storage
  prefixes.

## 025 — Site header

Shipped: 2026-09-11

**What changed**
- `SiteHeader` (`frontend/src/components/SiteHeader/`): one row above
  every open surface — the `superCPE` wordmark (text only, linking to
  `roleHome(account.role)` when signed in and `/` when not), the links
  that belong to the viewer's role, the signed-in email, and Sign out.
  Signed out: Courses, How it works, Sign in, Create account.
  Participant: My courses, Courses, Account, email, Sign out. Reviewer:
  Review, email, Sign out; admin gets the reviewer row if the null rule
  below ever changes. It returns null while either the session or the
  site read is unanswered, while the site's face is coming-soon, under
  `/admin`, and on `/change-password`. Sign out calls `signOut()` and
  navigates to `/`.
- `frontend/src/site/SiteContext.jsx`: `SiteProvider` reads
  `GET /api/v1/site` once on boot and exposes `{ site, loading, failed }`
  with SiteGate's failure posture (a failed read is not fatal);
  `useSite()`; and **`siteFace()` / `useSiteFace()`** — the one
  coming-soon decision, answering `loading`, `coming_soon`, or `open`
  in exactly the order the old SiteGate evaluated it (failed → open
  first, then loading, then `site_mode === "open" || account`).
- `SiteGate` now consumes `useSiteFace()` instead of owning the request.
  Its decision is unchanged and its comment block kept; the one
  `/api/v1/site` request is now shared with the header.
- `App.jsx`: `SiteProvider` wraps `<SiteHeader />` and `<Routes>` inside
  `SessionProvider`. Routes untouched.
- `SessionContext.signOut` clears the account inside
  `startTransition`. React Router 7 applies location changes as
  transitions; as a normal update the emptied session rendered first, on
  the old participant path, and `RequireRole` bounced it to `/login`
  before the header's `navigate("/")` was reached (reproduced in the
  test; deterministic, not a race). With both updates in the transition
  lane they commit in one render. `AdminNav`, `MyCourses`, and
  `ReviewHeader` still navigate to `/login` after signing out, which is
  also where `RequireRole` sends them, so nothing there changes.
- `frontend/src/components/SiteHeader/SiteHeader.test.jsx` renders the
  real `App` in a `MemoryRouter` with `/site` and `/auth` mocked and
  pins acceptance 1–6: four links and the wordmark href signed out at
  open, with Sign in reaching the login form; **no `<header>` or `<nav>`
  in the document** on `/`, `/courses`, `/courses/ATO`, and an unmatched
  path while coming_soon and signed out; a participant in coming_soon
  gets the header, and Sign out calls logout once and lands on the
  coming-soon page; `/admin/courses` as admin has no site nav and exactly
  one Sign out; a reviewer gets the header on both review pages; no
  header on `/change-password`; the header's text contains no course
  fact and no Registry string.
- `docs/OPERATIONS.md`: one bullet on cookie-clearing versus Sign out.
- Backend: no file touched. Suite 453 passed before and after.

**Standards touched**
- 8.01 / 8.01(11) — read in `docs/2026-Statement-on-Standards-for-CPE-
  Programs.pdf` (page 20–21). The header is chrome and discloses
  nothing, but a Courses link over the coming-soon page would be the
  partial disclosure 024 ruled out. The header and SiteGate therefore
  share `siteFace()` rather than each testing `site_mode`, so the
  header cannot render where the landing page does; the test asserts on
  the absence of header markup. The component contains no "National
  Registry", no sponsor ID, no sponsor statement, no course fact, and
  never reads `may_claim_registry` or `sponsor_name`.
- 4.05.3(1), (4) — read on page 7–8. Recon: `/how-it-works` was already
  linked from `/my/courses` ("How a course works") and the course page
  ("How this course works"), as 011's COMPLIANCE row says. The header
  adds a link from every open signed-out surface; a small reachability
  improvement, not a new way of satisfying the paragraph. COMPLIANCE.md
  is unchanged — the header satisfies nothing itself.

**Decisions**
- Task 2 took the provider, not the duplicate-request fallback. It broke
  no test; the existing SiteGate comment is still accurate and kept.
- 015's "/login is deliberately not linked from any page" rule was about
  the coming-soon landing page, which must not advertise what is behind
  it. It was never a rule against a Sign in link on the open site. The
  header does not render in coming_soon, so the landing page still links
  nothing; the rule is untouched, not reversed. Login.jsx's own comment
  still says "not linked from any page" and is now true only of the
  landing page; left as is.
- Sign out lands on `/`, not `/login`: the public face of the site. In
  coming_soon that is the landing page, which is correct. AdminNav keeps
  its `/login`.
- `/admin` null rule matches `/admin` and `/admin/...` exactly, not any
  path merely beginning with the letters.
- Recon (task 1), reported as found:
  - `/policies` is linked from the course page (each `PolicyLink` from
    the 016 payload) and from `/register` (the registration/attendance
    policy beside the submit button, 017). Nothing else links it.
  - `Login.jsx` offers no create-account link, and renders the form even
    when a session already exists. `Register.jsx` links `/login`.
  - `AdminNav` is rendered by the twelve `Admin*` pages only, all under
    `/admin/*`; `AdminCoursePreview` renders it only for the admin role,
    so a reviewer on `/admin/courses/:code/preview` sees neither
    `AdminNav` (role) nor the site header (path). Recorded below.
  - Breadcrumbs exist on `CoursePage`, `Account`, `HowItWorks`,
    `Policies`, `MyCourse`, `MyLesson`, `MyAssessment`, and
    `ReviewCourse`; all kept — a breadcrumb and a header are different
    things. `Login` and `Register` render their own large wordmark above
    the form; also kept.
  - `MyCourses` already had its own page header with the email, an
    Account link, and a Sign out button; `ReviewHome`/`ReviewCourse`
    share `ReviewHeader` with a wordmark, the email, and Sign out. So a
    participant on `/my/courses` did have a way out; the spec's "no way
    to sign out" holds for every other participant surface (`/account`,
    the course page, the reader, the player, the assessment). Both
    page-level headers were left in place — the spec says report, and
    neither file is in scope — but they now duplicate the site header.
    Recorded as a gap.
  - `usePageTitle` only sets `document.title`; nothing assumes it is the
    only thing above `<main>`.
- 320px was verified with a headless-Chrome screenshot of the built app
  in a 320px iframe (Chrome's minimum window is ~500px, so a bare
  `--window-size=320` lies): the nav drops below the wordmark and its
  links wrap right-aligned; no horizontal overflow.

**Known gaps**
- Duplicate chrome: `/my/courses` shows two Sign out buttons and the
  email twice; `/review` and `/review/courses/:code` likewise. Removing
  the page-level rows from `MyCourses` and `ReviewHeader` is a small
  follow-up.
- Deleting the session cookie signs the browser out but leaves the
  `sessions` row valid until idle or absolute expiry; only
  `POST /auth/logout` (Sign out) revokes it. Noted in OPERATIONS.md.
- No footer. `/policies` is linked from the course page and the register
  page and from nowhere else; 8.01.1's "available" is met where a
  purchaser sees it, but a footer would be better. Separate decision.
- `/login` has no create-account link and no "signed in as" affordance;
  a tester with a live participant session who opens `/login` sees the
  form. The header now shows Create account on `/login`, which covers
  the first half.
- A reviewer on `/admin/courses/:code/preview` has no chrome at all
  (`AdminNav` is admin-only there, the site header is null under
  `/admin`). Pre-existing for `AdminNav`; the header's `/admin` rule
  keeps it that way.
- `siteFace()` still relies on `SessionProvider` being above
  `SiteProvider`; nothing enforces the order beyond `App.jsx`.
- No frontend change to `frontend/dist/`; the build for the screenshot
  went to a scratch directory.

## 026 — Prove Stripe against production before the flip

Shipped: 2026-09-11

**What changed**
- Webhook exemption: `POST /api/v1/stripe/webhook` no longer sits behind
  `require_site_open_or_session`. The router-level dependency in
  `backend/app/routers/stripe_webhook.py` is gone and the route is
  allowlisted by name in 015's `INTENTIONALLY_PUBLIC`
  (`backend/tests/test_site.py`) with the argument in two sentences.
  **This feature touches the allowlist. That is a deliberate reversal
  of a deliberate decision** — 018's acceptance item 5, "router walk
  green, allowlist untouched". Behavior is otherwise unchanged: an
  unsigned request gets the same 400 `{"detail": "Invalid webhook
  signature"}` in both modes; no hint, reason, or route name was added.
- Live keys required to open: `stripe_non_live_key_vars` and
  `STRIPE_LIVE_KEY_PREFIXES` in `backend/app/config.py` (prefix check,
  `sk_live_` / `pk_live_`, never a call to Stripe). The open gate gained
  the `payments_test_keys` block finding (`launch_findings` in
  `backend/app/services/readiness.py`), one per offending variable, in
  the existing 422 `{"errors": [...]}` shape; it fires only when all
  three STRIPE_* values are set, so it never doubles
  `payments_not_configured`. `preflight` (`backend/app/cli.py`) reads
  `site_mode` through the CLI's own session and fails when the site is
  already `open` and either key is not live-prefixed, naming the
  variable — a refused deploy with the old version serving. When
  `site_mode` cannot be read (first deploy: preflight runs before
  `alembic upgrade head`, so the table does not exist) it prints a note
  and skips; there is no open site to protect. Boot is untouched: a
  closed site on test keys runs on purpose.
- `payments.livemode`, nullable boolean, migration `b7e3f9c2a815`.
  Set from Stripe's Checkout Session object at `start_checkout` (the
  gateway's `CheckoutSession` gained `livemode`) and re-stamped from the
  completion event's object (`_handle_completed`), never inferred from
  the key prefix — the rule 018 applied to amount and currency. No
  backfill; rows predating the column keep null (none in production).
  Recorded and displayed, never branched on. Docstring says exactly
  that a test transaction is thereby permanently and honestly
  distinguishable without anything being deleted (9.02).
- Admin: `AdminPaymentOut` carries `livemode`; `/admin/payments` shows a
  quiet muted "Test" marker beside the Stripe id on `livemode = false`
  rows, and the dashboard link goes to
  `https://dashboard.stripe.com/test/payments/…` for them
  (`frontend/src/pages/AdminPayments/stripeDashboard.js`); live and
  null rows link as before. New `AdminPayments.test.jsx` (3 tests).
- `docs/OPERATIONS.md` "Payments (018)" rewritten as the section 018
  specified and never got: account creation as the LLC, statement
  descriptor = `sponsor_profile.name` and why, restricted-key scopes
  named concretely (Checkout Sessions write; Payment Intents, Charges,
  Refunds read), the webhook registered **twice** with the bold warning
  that the two endpoints have different signing secrets and
  `STRIPE_WEBHOOK_SECRET` must be swapped in the same edit as the keys,
  the 10-step production verification run with its log table, the
  refund runbook stating plainly that the flag is not a bug, and what
  preflight and the open gate each refuse with the message each gives.
  Opening day step 4 now says the transport was proven in advance and
  what remains is the key swap plus one live smoke purchase (step 8).
- Test env: conftest's dummy keys are now `sk_live_dummy` /
  `pk_live_dummy`; the refusal tests swap in test-shaped ones. The
  check was not weakened to fit the fixtures.
- Tests: 464 passing (11 new; 025 had 453). Router walk green with
  exactly one allowlist addition. Unsigned webhook refused
  byte-identically in both modes; a signed completion processed
  identically in both modes (payment paid, one enrollment, one-year
  expiry, identical bodies); no webhook response in either mode carries
  the course title, code, price in cents or dollars, credit figure,
  participant email, or "National Registry"; `livemode` recorded from
  the stubbed session as False under live-shaped keys, re-stamped from
  the completion object, left alone when the event carries none, shown
  on `/admin/payments`; open gate refuses each test-shaped key naming
  it and passes with live-shaped ones; preflight fails on an open site
  with a test key naming only that variable, passes open with live
  keys, is silent while coming_soon, and skips with a note when
  `site_mode` is unreadable. 018's "three routes 404 in coming_soon"
  test was rewritten for the reversal: checkout and status still 404,
  the webhook answers 400. Frontend: 30 passing (3 new).

**Standards touched**
- 9.02 — read in `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`
  (page 22): "retain adequate documentation … for a minimum of five
  years". The verification run leaves a real sandbox payment, refund,
  and voided enrollment in production's tables; nothing deletes them,
  and `livemode` is what lets them stay without being mistaken for
  money. COMPLIANCE.md gained an update row on the 018 9.02 row saying
  so, and recording that the run had not yet been performed.
- 009's gate property ("a closed site does not advertise what is behind
  it") — verified, not assumed: `require_site_open_or_session` refuses
  with a bare 404 and protects course facts, prices, and the catalog's
  existence from anonymous visitors. The webhook's two possible bodies
  (`{"detail": "Invalid webhook signature"}` and `{"received": true}`)
  carry none of that, which the new test pins in both modes. The
  exemption reveals only that supercpe.com has a Stripe integration,
  which the checkout redirect announces to every customer anyway. No
  other protected property was found; the mechanism is per-router, so
  removing the dependency from this one-route router exempts exactly
  one route.

**Decisions**
- Recon (task 1), reported as found:
  - The gate was applied at router level
    (`APIRouter(dependencies=[Depends(require_site_open_or_session)])`)
    on a router carrying only the webhook route.
  - `INTENTIONALLY_PUBLIC` lives in `backend/tests/test_site.py` with
    seven entries (health, site, login, logout, landing, waiting-list,
    sitemap); the walk asserts every allowlisted route answers not-404
    anonymously in `coming_soon` and every other route answers 401 or
    404.
  - Unsigned request before this feature: 400 `{"detail": "Invalid
    webhook signature"}` at open, 404 `{"detail": "Not found"}` in
    coming_soon.
  - Preflight read only the env file, Spaces, and ffprobe — no DB value
    — but it can reach the database: it runs from the api image against
    the production env file, and `create-admin` on the same module
    already uses `SessionLocal`. So the check went into preflight as
    specified, not API boot; the first-deploy case (no tables yet) is
    handled by the skip-with-note above.
  - The gateway did not capture `livemode`; `verify_webhook` returned
    the whole event dict (which carries it at the top level and on the
    object), and `create_checkout_session` discarded it.
  - Dashboard links were built for live mode only
    (`https://dashboard.stripe.com/payments/{id}`); a test id 404s
    there. Fixed to respect `livemode`.
- `livemode` is stamped at checkout as well as at completion, so a
  `pending` row is already honest about its mode; the completion event
  re-stamps from the object, and an event with no `livemode` at all
  leaves the value alone rather than guessing.
- Prefix detection covers "empty" as well as "test-prefixed": on an
  already-open site, preflight also refuses a blank key by name. The
  open gate reaches that case through 018's `payments_not_configured`
  first, so the two findings never both fire.
- The CLI's session factory is monkeypatched to the test engine in
  `test_preflight.py` (autouse) so no preflight test reads the
  developer's dev database.
- `stripeDashboardUrl` lives in its own module rather than beside the
  component: oxlint's react-refresh rule flags non-component exports
  from component files.

**Known gaps**
- **The task 6 verification run was not performed.** Acceptance 8 is
  open. The build session had no Stripe sandbox keys (none in the local
  `.env`), no dashboard access, no browser, and the droplet refused its
  SSH key. The procedure is written in OPERATIONS.md with a log table
  whose first line says "Not yet run"; when the operator runs it, the
  date and outcome go there and in a new CHANGELOG entry, never by
  editing this one.
- Stripe disables webhook endpoints after sustained delivery failures;
  the sandbox endpoint may be disabled by flip time if it sits idle and
  failing. The runbook says to check its status, not assume it.
- Nothing verifies that `STRIPE_WEBHOOK_SECRET` belongs to the same
  mode as the keys. Candidate, not built: compare `livemode` on the
  first received event against the key prefix and log loudly on
  mismatch. The runbook's swap step is the only control.
- The restricted-key scope list is the app's actual call surface plus
  the reads the refund runbook wants; whether Stripe requires Products
  write for inline `price_data` under a restricted key is recorded as
  "if it refuses, add it" rather than asserted, because it was not
  exercised.
- ROADMAP.md's 018 line still says "every public route 404s in
  coming_soon"; it is now true of every public route but the webhook.
  Not edited: out of scope for this feature.
- The `/admin/sponsor` launch-findings panel renders the new finding's
  message through the existing generic list; no frontend change was
  needed, and none was made.

## 027 — Participant flow: every screen names the next step
Shipped: 2026-09-12

**What changed**
- Task 0 (recon), answered before code was written:
  1. `ATO` is text-first, so the walkthrough's clip was a supplemental
     clip inside the reader. They do render today
     (`frontend/src/components/Reader/Reader.jsx`, a `<video controls>`
     at the clip's `after_section`, no seek handler). W3 applied to the
     reader clip: nothing happened on `ended`. W4 on a reader clip is
     not a lock — native controls seek freely and both the local media
     route (`FileResponse`, Range-aware) and Spaces presigned URLs honor
     Range requests. On the video-only player the participant sees no
     seek control at all: no native controls, only Play/Pause and Mute
     beside a thin bar.
  2. Backward seeking on the video-only player already worked: `seekTo`
     clamps to `[0, furthest]` and `handleSeeked` undoes only a forward
     seek past the furthest point. It was reachable only by clicking the
     bar or the arrow keys. **Not a fix — a control added** ("Rewind
     15 s", `REWIND_SECONDS` in `Player.jsx`).
  3. The reader receives one `sections[]` array in manifest order with
     `locked` and `markdown: null` per locked section, plus `questions[]`
     (`after_section`, `answered`) and `media[]` (`after_section`). The
     stepper was built on that payload unchanged; `reader.build` and
     `schemas/reader.py` are untouched.
  4. `assessment_available`, `assessment_unavailable_reasons`, per-lesson
     `done`/`review_answered`/`review_total`, `retakes_remaining`,
     `failed_attempts`, and `open_attempt_id` are on the enrollment
     detail (`GET /api/v1/my/enrollments/{id}`) only; the reader payload
     has none of them. `MyLesson` already fetched the detail to choose
     the medium; it now keeps it and refetches it after every graded
     answer.
  5. A failed enrollment attempt's result carries `retakes_allowed` and
     `retakes_remaining` (integers) beside `score_pct`, `passing_pct`,
     `correct_count`, `question_count` (`result` in
     `backend/app/services/assessment.py`). Preview attempts carry no
     `retakes_remaining`. The assessment info (`MyAssessmentInfo`) also
     carries both.
  6. `/policies` renders `retake_policy_text()` under "Assessment and
     re-takes" with no anchor. It now has `id="retakes"`; the failed
     result and the course page link `/policies#retakes` and do not
     restate it.
- Reader as a section stepper (`frontend/src/components/Reader/Reader.jsx`,
  `Reader.module.css`, new `stepper.js`): one section on screen; a
  contents column (sidebar from 60rem, a "Contents" toggle below) listing
  every section as read / current / unread / locked, with glossary and
  appendix under "Reference"; a locked entry is a disabled title marked
  Locked. Front matter first, always ("Start here"); body sections show
  "Section N of M" and a thin bar; reference sections say "Reference"
  and offer "Back to the guide". Questions placed after the current
  section render inline beneath it, all of them, in package order;
  Continue is disabled with the hint "Answer the review question above
  to continue" until every one is answered, then opens the next section
  — calling the page's `onContinue` (a refetch) first, so it shows what
  the server unlocked. Position is `?section=<key>` in the URL (reload
  and back/forward work; nothing written to the server); with no
  section in the URL the reader lands on the section after the last
  passed gate (`resumeKey`), or front matter when no gate has been
  passed. Search hits and glossary entries with a `section_key` in this
  lesson set the URL position. Left/right arrow keys step; no new
  dependency.
- Completion call to action: after the last body section, once every
  question in the lesson is answered, a card names the next step from
  `deriveNextStep` (`frontend/src/pages/MyLesson/nextStep.js`): the next
  lesson not yet `done` (in position order), else "Take the qualified
  assessment" / "Re-take … (N left)" when `assessment_available`, else
  "Resume the assessment" for an open attempt, else the course page.
  `MyCourse` shows the next action as a primary button under the
  deadline ("Continue reading (lesson 2 of 3)", "Continue watching …",
  "Take the qualified assessment", "Re-take the qualified assessment (N
  left)", "Resume the assessment", "View your certificate"); `/my/courses`
  cards carry the same labels ("Continue reading" by `lessons_kind`).
- Video direction and controls: reader clips keep `controls` and no seek
  handler (test pins a settled seek standing) and show "Continue
  reading" on `ended`, which scrolls to the open question after the
  section or opens the next section. The video-only player
  (`frontend/src/components/Player/Player.jsx`) gains "Rewind 15 s" and
  an end panel: the remaining review questions when the enrollment says
  any are unanswered (asked again in place — a reload mid-question
  resumes past the review point and never re-asks it), else the derived
  next step, else "End of this lesson." in the preview; "Watch again"
  beside it. Forward-seek lock untouched (test pins the refusal).
- Failed-result and exhausted wording
  (`frontend/src/components/Assessment/Assessment.jsx`, new
  `frontend/src/components/RetakesExhausted/`): with sittings left —
  score, threshold, "You have N re-takes left on this enrollment", a
  "Re-take the assessment" button, "Back to the study guide" (or "Back
  to the lessons" on a video course); with none — score, threshold, "You
  have used all N re-takes on this enrollment", "Read the re-take
  policy" → `/policies#retakes`, "Contact us about re-enrolling:
  <address>", and "The study guide stays open: you can keep reading
  it". The course page renders the same notice once, in the next-action
  slot, and drops its "Qualified assessment" section in that state;
  "The assessment is not available yet" is now only shown for unanswered
  review questions (the "No re-takes left" reason is filtered out of the
  list). `MyCourse` reads `retakes_allowed` from the assessment info
  only when exhausted (the detail carries the sittings left, not the
  allowance).
- Video-wording grep (section 5), participant surfaces, as found:
  `pages/MyCourses/progressLabel.js` (kind-aware, kept),
  `pages/MyCourse/MyCourse.jsx:176` (a comment), `pages/MyLesson/
  MyLesson.jsx` (medium dispatch), `pages/Catalog/Catalog.jsx` ("N
  minutes of video", shown only for video lessons with ≥1 minute, kept),
  `components/Assessment/retryAdvice.js` (kind-aware, kept),
  `components/Reader/Reader.jsx` (the clip caption "Watch, skip, or
  replay it as you like", about a clip, kept), `components/Player/
  Player.jsx` ("Re-watch this section", the video player, kept). One
  miss found and fixed: the `/how-it-works` text
  (`backend/app/services/instructions.py`) said "consider re-watching
  the lessons before trying again" for every course; it now says
  "re-reading the guide, or re-watching the lessons".
- Chrome: `MyCourses` keeps only its heading (email, Account link, and
  Sign out were the header's); `ReviewHeader` is removed from
  `ReviewHome.jsx` and `ReviewCourse.jsx` along with its CSS — after
  dropping its email and Sign out only a second wordmark remained.
  `/login` shows "New here? Create account" below the form under
  `siteFace() === OPEN`. New `frontend/src/components/SiteFooter/` under
  exactly the header's rule (null while loading or coming-soon, under
  `/admin`, and on `/change-password`): links `/policies`,
  `/how-it-works`, and the sponsor's contact address (mailto). Mounted
  in `App.jsx` after `<Routes>`.
- Backend (two small changes, both reported): `SponsorProfilePublic`
  gains `contact_email` and the public `GET /api/v1/sponsor` serves it
  (`backend/app/schemas/sponsor.py`, `backend/app/routers/sponsor.py`;
  new test `test_public_endpoint_carries_contact_email` pins the field
  and that nothing else joined it) — the address was in no
  participant-facing payload and the spec asks for it on two surfaces;
  and the instructions wording above. Suite 464 → 465 (the one new
  test). No model change, no migration.
- Frontend tests 30 → 73: `Reader.test.jsx` (D2 kept and extended
  through the stepper: the verdict survives leaving and returning; one
  section at a time; locked entry title-only and its body absent from
  the DOM; Continue disabled/enabled; progress counts body sections;
  URL round-trip and fallback; resume landing; no `is_correct`,
  `correct_choice_key`, or feedback text in the DOM before grading;
  completion card conditions and next-lesson variant; clip `controls`,
  no seek lock, `ended` affordance), `stepper.test.js`,
  `nextStep.test.js`, `Player.test.jsx` (backward seek and rewind,
  forward refused, end panel variants), `Assessment.test.jsx` (both
  failed variants and the preview, nothing per question),
  `SiteFooter.test.jsx` (footer present at open with and without the
  sponsor read, absent in coming-soon / under `/admin` /
  `/change-password`, no course fact or Registry string; `/login`
  Create account at open and not in coming-soon signed out; one Sign
  out and one email on `/my/courses`, `/review`, `/review/courses/ATO`).
- COMPLIANCE.md: four rows appended (4.05.3 item 4, 5.01.2.1, 6.01.2
  re-takes, 8.01.1). ROADMAP.md: the 028 improvement note.

**Standards touched**
- 4.05.3 items 4 and 5 — read in `docs/2026-Statement-on-Standards-for-
  CPE-Programs.pdf` on printed pages 7–8. The front matter that answers
  item 4 renders first in the stepper and is never hidden; item 5's
  review questions render inline with feedback as before.
- 5.01.2.1 — page 9. Placement is the package's `after_section`; the
  stepper moves, batches, and defers nothing, and adds no gate of its
  own.
- 5.01.2.2 — page 10. Feedback stays on screen through the stepper and
  through leaving and returning to a section.
- 6.01.2 — pages 13–14. "The number of re-takes … is at the sponsor's
  discretion": the failed result now says what the count means and
  links the published policy; sub-ii-b-1, "may not provide feedback":
  still nothing per question on a failed attempt, asserted in both
  variants.
- 8.01.1 — page 20. The footer adds a second path to `/policies`; the
  policies themselves are unchanged.

**Decisions**
- The reader's "read" state for an ungated section is browser state: the
  payload can say which gates are passed and what is locked, not
  whether a section between gates was read. Sections before the resume
  point are marked read from the payload; sections this session moved
  on from are marked read locally; nothing is written to the server. A
  server-side reading position would be a new participant record and
  needs a retention decision — not built, as the spec anticipated.
- "Continue reading (Section 4 of 14)" on the course page and
  `/my/courses` is rendered as "(lesson 2 of 3)": the enrollment payload
  carries lessons and their question counts, not section counts, and the
  spec says to add no field.
- The contact address is served from the already-gated public `/sponsor`
  payload rather than `/site` (which is public in coming_soon) — the
  footer and the exhausted notice render only at open or with a
  session, so the gate matches the surfaces.
- `ReviewHeader` removed entirely rather than trimmed (see above).
- `isExhausted` lives in `pages/MyCourse/exhausted.js` — oxlint's
  react-refresh rule flags non-component exports from component files
  (the 026 `stripeDashboard.js` precedent).
- On the course page the exhausted allowance `N` is read from the
  assessment info when needed; `failed_attempts - 1` is the fallback
  while that read is in flight (exact under the current invariant that
  `start_for_enrollment` refuses at zero sittings).

**Known gaps**
- Acceptance 1–5 (browser) and 7 (production): not yet run by the
  operator.
- `/policies#retakes` scrolls only if the section exists when the hash
  is applied; the page loads its payload asynchronously, so a direct
  navigation may land at the top — the same caveat as 016's
  `/policies#refund` links.
- The reader contents column and the 320px layout were verified by
  tests and a production build, not by a screenshot; 025 used headless
  Chrome for that and 027 did not.
- `MyLesson.jsx` still resets its state synchronously inside its load
  effect (a pre-existing pattern oxlint warns about); `Player.jsx`'s
  unused `furthest` state variable predates this feature.
- The reader clip's `ended` affordance scrolls to the open question or
  opens the next section; it does not auto-advance, by design.
- On a video-only lesson, "Answer the review questions" re-asks every
  question in the lesson, not only the unanswered ones — the play
  payload carries no `answered` flag and adding one is a payload change
  this feature did not make.
- `deploy/`, `docs/OPERATIONS.md`: unchanged.

## 028 — Unlimited re-takes and free renewal after expiry
Shipped: 2026-09-12

**What changed**
- `RETAKES_ALLOWED` in `backend/app/constants/assessment.py` is
  `None` (unlimited), typed `int | None`, with the comment rewritten:
  6.01.2 leaves the count to the sponsor; `None` is unlimited; an
  integer is re-takes after the first sitting per enrollment; every
  attempt is retained whatever the value; 011's policy text renders
  whichever it is.
- `enrollments.retakes_remaining` returns `None` when unlimited;
  `assessment.start_for_enrollment` skips the sittings check on `None`
  (the other refusals — completed, expired, voided, unanswered review
  questions, open attempt — are unchanged and re-proven). The failed
  result, the assessment info (enrollment and preview), and the
  enrollment card carry `retakes_allowed` and `retakes_remaining` as
  nullable, with `retakes_unlimited: bool` beside them.
- `policies.retake_policy_text()` branches: unlimited renders "A
  participant may re-take the qualified assessment as many times as
  needed."; an integer renders the 010 sentence. The how-it-works page
  (`services/instructions.py`) branches the same way and gains one
  sentence on renewal at no charge.
- Free renewal: `enrollments.renewal_refusals` (derived from `paid`
  payment rows and enrollment statuses, never stored), `renewable`
  (per expired card: the most recent enrollment on the course, and
  eligible), and `renew` (the one constructor with
  `source="renewal"`, no Stripe call, no payment row).
  `POST /api/v1/courses/{code}/renew` in `routers/courses.py`, behind
  the site gate and the participant role, one 422 line per failed
  condition (no paid purchase; still active; already completed;
  voided; no enrollment at all), 404 for an unknown course, 422 for an
  unpublished one; answers the new enrollment as the `/my/courses`
  card (`my.enrollment_summary`, now public).
- `enrollments.source` CHECK gains `renewal`: migration
  `c2d8e5f1a028_enrollment_source_renewal.py`, written by hand; no
  other schema change; no FK from the renewal to the payment or the
  expired enrollment.
- 018 narrowed: `payments.start_checkout` refuses a participant with a
  prior `paid` row for the course ("you have already purchased this
  course; renew it from the course page instead of paying again"); the
  active-enrollment refusal drops its "it can be purchased again after
  it expires" clause. Pending-session reuse is unchanged.
- Frontend: `MyEnrollmentSummary.renewable` drives a shared
  `RenewEnrollment` component (`frontend/src/components/RenewEnrollment/`)
  — "Start a new enrollment (no charge)" — on the course page's
  Registration section (re-renders enrolled in place), the `/my/courses`
  card and the enrollment page's next action (both navigate to the new
  enrollment). A shared `retakeLabel` in `pages/MyLesson/nextStep.js`
  drops the "(N left)" count when `retakes_remaining` is null; the
  failed result shows score, threshold, and "Re-take the assessment"
  with no count under the unlimited policy; the intro sentence says the
  assessment may be re-taken as many times as needed. `RetakesExhausted`
  and `isExhausted` are untouched and render only at
  `retakes_remaining === 0`. The admin enrollments table gains a Source
  column.
- Tests: backend 465 → 481 (`tests/test_renewal.py` new: the
  eligibility matrix, pinning to current packages, retention of the
  expired enrollment's answers and attempts, admin sources, only the
  latest expired card renewable, the gate; `set_retakes_allowed` in
  `conftest.py` patches every module that binds the constant for the
  finite tests). Frontend 73 → 82 (`CoursePage.test.jsx` and
  `MyCourses.test.jsx` new; Assessment and nextStep tests extended).
  Router walk green; `INTENTIONALLY_PUBLIC` untouched.

**Task 0 answers**
1. `enrollments_service.enroll` accepts `source="admin"` (default; the
   admin enrollments router) and `"purchase"` (the Stripe webhook).
   Constrained by CHECK `ck_enrollments_source` in
   `backend/app/models/enrollment.py` and migration `b3e9c41a7f52`;
   `ENROLLMENT_SOURCES` mirrors it. `renewal` needed a hand-written
   migration (above).
2. `retakes_remaining` was consumed by: `assessment.start_for_enrollment`
   (`== 0` refusal), `assessment.result` (failed payload),
   `routers/my.py` `_unavailable_reasons` (`== 0`), `_summary_fields`
   (`retakes > 0` gating `assessment_available`, and the field),
   `get_assessment` (`retakes > 0` gating `available`); schemas
   `MyAssessmentInfo` and `MyEnrollmentSummary` typed it `int`, and
   `AssessmentInfo.retakes_allowed: int`; `services/instructions.py`
   interpolated `RETAKES_ALLOWED` into the how-it-works markdown;
   `policies.retake_policy_text`. Frontend: `Assessment.jsx` (failed
   branch and intro), `RetakesExhausted.jsx`, `MyCourse.jsx`,
   `MyCourses.jsx`, `nextStep.js`, `exhausted.js`. The `> 0` gates became
   `!= 0` so `None` passes; everything else handles null.
3. Tests asserting the exhausted message or an integer:
   `test_completion.py::test_start_refused_when_retakes_exhausted`
   (looped `1 + RETAKES_ALLOWED`, asserted the number and the word
   `RETAKES_ALLOWED` in the message) and
   `::test_failed_enrollment_result_carries_no_feedback` (equality to
   the constant); `test_policies.py::test_retake_text_carries_the_enforced_numbers`
   and `::test_how_it_works_numbers_match_the_constants`
   (`f"{RETAKES_ALLOWED} times"`); `test_assessment.py::test_failed_result_payload_has_no_feedback`
   (equality, still true with `None`). Frontend: `Assessment.test.jsx`
   (finite fixtures) and `nextStep.test.js` ("(3 left)"). The first
   four became finite-policy tests under `set_retakes_allowed`; the
   frontend ones keep their finite fixtures and gained unlimited cases.
4. 018 on an expired participant calling checkout: refused only on an
   *active* enrollment, so it minted a second Stripe session and a second
   `payments` row, and the webhook created a second `purchase`
   enrollment (`test_expired_enrollment_allows_a_fresh_purchase` proved
   exactly this). Confirmed before narrowing.
5. Policy text lives in `policy_versions` only; no seed. The test factory
   `publish_test_policies` in `tests/conftest.py` publishes "Test {kind}
   policy." for each kind. The admin path is `POST /api/v1/admin/policies`
   (`policies.admin_router` → `policies_service.publish`, append-only,
   effective-dated), reached from the admin sponsor page. Nothing in
   code reads the body, so the factory does not need a policy that
   mentions renewal.

**Standards touched**
- 6.01.2 — "The number of re-takes … is at the sponsor's discretion"
  (page 13); unlimited chosen; sub-ii-b-1 on page 14 (no feedback on a
  failed assessment) untouched and re-asserted by the same tests.
- 9.02.2(3) — expiration "no longer than one year from the date of
  purchase or enrollment" (page 24); a renewal is a new enrollment with
  its own year; nothing is extended.
- 8.01 items 8 and 9 — registration and refund policies (page 20); the
  registration policy must state the renewal rule (operator, below);
  the refund policy is unchanged.
- 8.01.1 — policies "formalized, published, and made available" (read
  on page 21, not page 20 as the spec said); the rule lives in the
  published policy, linked, not restated.

**Decisions**
- **Reversal of 018's "re-purchase allowed after expiry":** checkout is
  for a first purchase of a course only; a participant with a `paid`
  row renews instead. The 018 test was rewritten as
  `test_renewal_after_expiry_checkout_refused`, and the 018
  active-enrollment refusal no longer promises a later re-purchase.
- `retakes_unlimited: bool` was added beside the nullable numbers: the
  failed result already used an absent `retakes_remaining` to mean "a
  preview attempt, no enrollment", so null alone could not tell the
  browser "unlimited" from "preview". The frontend keys the Re-take
  button on the flag and the enrollment case on the key's presence.
- `renewable` is true only on the participant's most recent enrollment
  on the course; an older expired card never offers the button.
- Eligibility lives in `services/enrollments.py` (it owns the
  constructor) and imports the `Payment` model directly; the payments
  service already imports the enrollments service, so the reverse
  import would have been circular.
- A renewal pins the course's *current* published packages. If the
  course was re-reviewed and republished since the expired enrollment,
  the participant reads the current guide; that is correct — the
  expired enrollment keeps its own pin.
- 029 subscriptions: a subscription source will be a second qualifying
  condition beside `has_paid` in `renewal_refusals`; one comment names
  it, nothing is built.
- How-it-works (code, 4.05.3 instructions) gained one sentence on
  renewal at no charge because a "None times" rendering would have been
  a bug and the page must not contradict the policy the operator
  publishes.
- Drafted registration/attendance policy wording (operator publishes as
  a new version):
  > Enrollment. An enrollment in a course begins on the date of purchase
  > or enrollment and expires one year later; the qualified assessment
  > must be completed before the enrollment expires. An enrollment is
  > never extended. A participant who purchased a course and did not
  > complete it before the enrollment expired may start a new one-year
  > enrollment in the same course at no additional charge from the
  > course page. The new enrollment begins with no review questions
  > answered and no assessment attempts, and uses the course's currently
  > published materials.
  >
  > Attendance. There is no attendance requirement; a self-study course
  > is completed by answering every review question and passing the
  > qualified assessment.
  >
  > Re-takes. A participant who does not pass the qualified assessment
  > may re-take it as many times as needed within the enrollment period.
  > No feedback on individual questions is given for an assessment that
  > was not passed.
- Local test database: `tests/conftest.py` builds it once with
  `create_all` and never alters an existing table, so the changed CHECK
  required dropping `supercpe_test`; done as a routine step (test data
  only).

**COMPLIANCE.md**
- Updated: four rows appended — 6.01.2 (re-takes), 9.02.2(3), 8.01
  item 8, 8.01 item 9.

**ROADMAP.md**
- The "028 — exhausted enrollments" improvement note 027 added is struck
  and superseded by this feature's line (append only).

**Known gaps**
- Acceptance 6 (operator publishes the new registration/attendance
  policy version) and 7 (production deploy and re-run of 1 and 2): not
  yet run by the operator.
- Acceptance 1–4 were proven at the API layer by the backend suite
  (five failures then a permitted start; renewal with a fresh year, no
  answers, no attempts; checkout refused with the already-purchased
  message and a first purchase of another course allowed; refunded then
  voided then expired shows no renewal and checkout is allowed). The
  browser walkthrough of the same steps was not performed in the build
  session.
- `assessment.result` for a *preview* attempt under the unlimited policy
  reports `retakes_unlimited: true`; the preview never counted sittings
  anyway.
- The local `supercpe_test` database was dropped and rebuilt; any other
  developer's test database needs the same once (the CHECK is not
  altered by `create_all`).
- Out of scope, reported not built: per-course retake limits; extending
  `expires_at`; renewal of a completed enrollment; subscriptions (029);
  any refund/void change; rewriting 027's exhausted wording. The
  CLAUDE.md "Commands" block still says "<typecheck and lint commands —
  fill in>"; this build used `npm run lint` (oxlint) and
  `python -m pyflakes app tests` (the only linters present) — no
  typechecker exists in either half.

## 029 — Annual subscription
Shipped: 2026-09-12

**What changed**
- Constants: `backend/app/constants/subscription.py` —
  `SUBSCRIPTION_PRICE_CENTS = 14900` (ours), `SUBSCRIPTION_PERIOD_DAYS =
  365` (ours; Stripe's yearly interval is the schedule), and the Stripe
  status lists the two new CHECKs mirror.
- Config: `STRIPE_SUBSCRIPTION_PRICE_ID` joined 012's all-or-nothing
  `STRIPE_VARS` (`backend/app/config.py`), so 018's
  `payments_not_configured` open-gate finding covers it; the "swap all
  three in one edit" wording became "all four" in config, readiness,
  preflight, `.env.example`, and OPERATIONS.md. `preflight`
  (`backend/app/cli.py`) retrieves the Price once through the boundary
  and, on an open site, refuses a deploy whose Price amount or currency
  differs from the constant (naming both numbers) or whose Price cannot
  be read; while coming-soon it prints a note. Not configured is silent
  (the open gate owns that).
- Data model, migration `d4b8e2a7c029`: `accounts.stripe_customer_id`
  (nullable, unique, set once); `subscriptions` (status CHECK, period,
  `cancel_at_period_end`, `canceled_at`, `credit_applied_cents`,
  `livemode`, plus `checkout_url` for live-session reuse);
  `subscription_invoices` (status CHECK, amount, currency, period,
  `livemode`, plus `stripe_payment_intent_id` so a refund can find the
  row); `payments.credited_to_subscription_id`; `enrollments.source`
  CHECK gains `subscription`. All hand-written; docstrings say financial
  record, never deleted, outlives `RETENTION_YEARS`.
- Boundary: `services/stripe_gateway.py` gained `create_customer`,
  `create_credit_coupon`, `create_subscription_checkout_session`
  (`mode="subscription"`, `payment_method_collection="always"`,
  `discounts=[{"coupon": …}]`, metadata on both the session and
  `subscription_data`), `retrieve_subscription`, `create_portal_session`,
  and `retrieve_price`. No second client.
- `services/subscriptions.py`: `current` (status `active` and
  `current_period_end` ahead, both as Stripe last reported; grace
  decided once, as none — `past_due` is not current), `enroll_subscriber`
  (010's constructor, `source="subscription"`, no Stripe call),
  `subscription_enrollable` (the card's "Enroll again (included)"),
  `credit_payments`/`credit_cents` (paid, uncredited, capped),
  `start_subscribe` (customer ensured and committed first, coupon only
  when credit > 0, row written `incomplete` before the URL returns,
  live incomplete session reused), `portal_url`, and the webhook
  handlers. Credit is consumed only by the completed-session handler,
  from `total_details.amount_discount`, with the payment FKs in the
  same transaction.
- Webhook: `payments.handle_event` stays the one dispatch point.
  `checkout.session.completed` with `mode == "subscription"` links the
  Stripe subscription id, re-stamps `livemode`, records the discount and
  the FKs, and copies status and period from one `retrieve_subscription`
  (the session object carries neither); `customer.subscription.updated`
  / `.deleted` copy status, period, `cancel_at_period_end`,
  `canceled_at` (found by Stripe id, else by the row id in the metadata,
  so an update that outruns the completion still lands); `invoice.paid`
  upserts the invoice row and syncs the period from the lines;
  `invoice.payment_failed` upserts the row as `open` and nothing else;
  `charge.refunded` on a subscription invoice marks it `refunded` and
  stops (018's `_handle_refunded` tries payments first, then invoices,
  then logs unknown). Orphans log loudly and answer 200; each new type
  is idempotent through the existing event table, recorded and committed
  with the handler's changes in one transaction.
- 028 join: `renewal_refusals` in `services/enrollments.py` — "or any
  prior `subscription`-sourced enrollment for the course" beside
  `has_paid`. 018 join: `start_checkout` refuses a current subscriber
  ("your subscription covers this course; enroll directly"). The renew
  route refuses a current subscriber the same way (the subscriber's
  enroll takes precedence), and the card never offers both.
- Routes: `POST /api/v1/courses/{code}/enroll` (201 the card; 422 per
  condition; 404 unknown course); `GET/POST /api/v1/subscribe`,
  `GET /api/v1/subscribe/me`, `POST /api/v1/subscribe/portal`,
  `GET /api/v1/subscribe/{session_id}/status` (owner-only) in
  `routers/subscribe.py`, all behind the site gate; `GET
  /api/v1/admin/subscriptions` in `routers/admin_subscriptions.py`.
  `MeOut` gained `subscription_current` (derived per read; false for
  non-participants); `MyEnrollmentSummary` gained
  `subscription_enrollable`; `AdminPaymentOut` gained
  `credited_to_subscription_id`.
- Frontend: `/subscribe` (offer from the payload, credit line only when
  > 0, both policy links, Subscribe → Stripe, sign-in links for
  visitors), `/subscribe/success` (polls, refreshes the session, links
  the catalog, 018's ~30s honest-delay state), `/account` Subscription
  section (none / current, renews on / cancels on / past due with
  "Update payment method" / lapsed; credit consumed; Manage subscription
  → Customer Portal), header Subscribe link for a participant without a
  current subscription (only while `site_mode` is open; null in
  coming-soon and under `/admin` as before), footer Subscribe link at
  open, course page two-choice section / included-enroll button /
  "Enroll again (included)" via the shared `SubscriptionEnroll`
  component (also on the `/my/courses` card, checked before 028's
  renewal), `/admin/subscriptions` (table, invoices, both flags, Void
  beside each active enrollment of a refunded subscription, Stripe link
  honoring `livemode`), `/admin/payments` credited marker, AdminNav
  link.
- Docs: OPERATIONS.md "Subscriptions (029)" (Product/Price, scopes,
  four new event types on both endpoints, portal configuration, dunning
  emails, Stripe Tax note, CLI walkthrough with its log table, the
  subscription refund runbook) and the Payments (018) section's counts
  and event list; four COMPLIANCE.md rows appended; `.env.example`.
- Tests: backend 481 → 523 (`tests/test_subscriptions.py`, 38, plus 4
  preflight price tests; 018's boot all-or-nothing test and 009's
  exact `/me` payload test extended); frontend 82 → 104 (header,
  course page, footer extended; Subscribe, Account, SubscribeSuccess
  new). Router walk green; `INTENTIONALLY_PUBLIC` untouched; every new
  route 404s anonymously in coming_soon; no new response carries a
  course fact or "National Registry".

**Task 0 answers**
1. `create_checkout_session` did not accept a mode — `mode="payment"`
   was hard-coded with inline `price_data`. Rather than a mode flag on
   a function whose line items, customer handling, and return shape
   differ, a separate `create_subscription_checkout_session` was added
   to the same boundary. `stripe==12.4.0` (API version
   `2025-07-30.basil`) supports Checkout `subscription` mode,
   `payment_method_collection="always"`, and `discounts=[{"coupon":
   …}]`, checked in its `Session.CreateParams`. Basil also moved
   `current_period_*` to the subscription item, `invoice.subscription`
   under `parent.subscription_details`, `invoice.payment_intent` under
   `invoice.payments`, and removed `charge.invoice`; the handlers read
   both shapes and copy whichever Stripe sends.
2. 018 created Stripe guest customers per Checkout (`customer_email`,
   no Customer object); no account carried a customer id. This feature
   adds `accounts.stripe_customer_id`, creates the Customer on the
   first subscription checkout, and never backfills guests.
3. `handle_event` dispatched on `checkout.session.completed`,
   `checkout.session.expired`, and `charge.refunded`; every other type
   was logged by name at INFO and answered 200 without a record. New:
   `checkout.session.completed` (subscription mode),
   `customer.subscription.updated`, `customer.subscription.deleted`,
   `invoice.paid`, `invoice.payment_failed`, and `charge.refunded` on a
   subscription invoice. Each is idempotent by event id through
   `stripe_webhook_events` (the replay check runs before dispatch; the
   new handlers record the event and commit in the same transaction).
   `customer.subscription.created` stays unhandled by design (below).
4. `renewal_refusals` in `backend/app/services/enrollments.py`, the
   `if not has_paid(db, account, course):` line; it became `if not
   (has_paid(...) or any(e.source == "subscription" for e in rows))`.
5. 026's key had Checkout Sessions Write and Payment Intents, Charges,
   Refunds Read. Missing for Billing, to be added by the operator:
   Customers Write, Subscriptions Read, Coupons Write, Billing Portal
   Write (sessions), Invoices Read, and Prices/Products Read (for
   preflight's `Price.retrieve`). Nothing was widened in code.
6. `Registration` in `frontend/src/pages/CoursePage/CoursePage.jsx`
   (018, revised by 028 for the renewal button); it gained the second
   option, the included-enroll button, and the "Enroll again" branch.

**Standards touched**
- 9.02.2(3) — read on printed page 24: "no longer than one year from
  the date of purchase or enrollment" for individual courses. A
  subscription is not an enrollment; each course enrolled under it
  carries its own year from enrollment through 010's constructor, and
  a subscription ending touches no enrollment. COMPLIANCE row appended.
- 8.01 items 8 and 9 — read on printed page 20; 8.01.1 on page 21
  ("formalized, published, and made available"). The subscription is a
  fee; `/subscribe` discloses price, term, renewal, cancellation, and
  links both policies. COMPLIANCE row appended; the operator's new
  policy versions are pending (below).
- 9.02 — read on printed page 22. `subscriptions`,
  `subscription_invoices`, and the credit FK are financial records
  retained beyond `RETENTION_YEARS`; a lapse deletes nothing. Two
  COMPLIANCE rows appended (retention; amounts as Stripe reported).

**Decisions**
- **Reversal of 018's "the webhook is the sole creator of
  enrollments":** a current subscriber's enroll is a click —
  `POST /courses/{code}/enroll` calls 010's constructor with no Stripe
  call and no payment row. The webhook remains the sole creator of
  *purchased* enrollments; `services/payments.py`'s docstring says so.
- **Reversal of 018's "the refund policy covers course sales":** it
  now also covers subscriptions. The webhook marks, the admin decides
  (018's rule kept); the admin subscriptions view raises two loud flags
  (refunded-with-current-subscription, refunded-with-active-enrollments);
  cancelling in Stripe is the admin's separate act.
- **Accepted sponsor exposure:** completed enrollments and issued
  certificates are immutable 9.02 records a refund cannot unmake. A
  participant who subscribes, completes courses, and is then refunded in
  full keeps that credit. Recorded here, and in the refund runbook.
- Status and period are never taken from the Checkout Session object
  (it carries neither): the completed-session handler retrieves the
  subscription once through the boundary and copies from it; if the
  retrieve fails the row stays `incomplete`, loudly, until
  `customer.subscription.updated` arrives. This keeps the registered
  event list at the four the spec named and keeps "copy, never infer"
  honest. `customer.subscription.created` is therefore unhandled.
- Two columns beyond the spec's list: `subscriptions.checkout_url`
  (the live-session reuse the spec asks for needs the URL, as
  `payments` keeps it) and `subscription_invoices.stripe_payment_intent_id`
  (`charge.refunded` carries a payment intent and, under basil, no
  `invoice`; without it a refund could not find the row).
- The status CHECK lists all eight Stripe subscription statuses, not
  the six the spec expected: `trialing` and `paused` cannot arise from
  this configuration, but a CHECK that refused a status Stripe sent
  would 500 the webhook and make Stripe retry forever. Neither is ever
  current.
- `past_due` is not current: no grace period, decided in `current`'s
  docstring. Stripe's dunning and the participant's "update your
  payment method" state are the whole handling.
- The header and footer Subscribe links render only while `site_mode`
  is open, not merely while the header's face is open: a signed-in
  participant on a coming-soon site sees the header (025) but not an
  offer whose page names a price.
- `subscription_current` rides on `/auth/me` (derived per read) so the
  header needs no second request; the success page calls the session's
  `refresh()` on landing.
- A current subscriber's expired course is re-started through the
  subscriber's enroll; the 028 renew route refuses them by name and the
  card never offers both buttons. A lapsed subscriber gets 028's
  renewal for courses started under the subscription.
- The `/admin/subscriptions` page reuses `AdminPayments.module.css`
  and the existing void endpoint; no new admin action exists.
- `tests/test_payments.py`'s `pay` helper reuses one event id and one
  intent id; the new suite's `pay_course` gives each purchase its own
  so multi-course credit can be computed. The local `supercpe_test`
  database was dropped and rebuilt for the new columns and CHECKs
  (test data only); the migration was applied to the local dev
  database with `alembic upgrade head` and the CHECKs inspected.
- Drafted registration/attendance policy wording (operator publishes as
  a new version, appended to 028's text):
  > Annual subscription. A subscription begins on the date of purchase,
  > runs for one year, and renews automatically at the end of each year
  > until cancelled. While a subscription is current, the subscriber may
  > enroll in any published course at no additional charge. Each course
  > enrolled in under a subscription is a separate enrollment with its
  > own one-year completion window from the date of enrollment; the end
  > of a subscription does not shorten or extend any enrollment already
  > started. If a subscription lapses, every enrollment, completion, and
  > certificate is retained, and the subscriber may subscribe again at
  > any time. Course purchases made before a first subscription are
  > credited, dollar for dollar and once, against the first subscription
  > payment, up to the subscription price.
- Drafted refund and cancellation policy wording (operator publishes as
  a new version):
  > Courses. A course purchase is refundable in full on request, with no
  > questions asked. When a purchase is refunded, access to that
  > enrollment ends; a completed course and its certificate stand.
  >
  > Subscriptions. The current subscription payment is refundable in
  > full on request, with no questions asked; refunds are never
  > pro-rated. A subscriber may cancel at any time from their account;
  > access continues to the end of the paid period and the subscription
  > does not renew. When a subscription payment is refunded, the
  > subscription is cancelled and access to enrollments still in
  > progress under it ends. Courses completed and certificates issued
  > before the refund stand; they are permanent records.
- The 018 restricted-key scopes the operator must add: Customers Write,
  Subscriptions Read, Coupons Write, Billing Portal Write, Invoices
  Read, Prices/Products Read (OPERATIONS.md "Subscriptions (029)").

**COMPLIANCE.md**
- Updated: four rows appended — 9.02.2(3); 8.01 items 8 and 9 with
  8.01.1; 9.02 (retention); 9.02 (018 payment row, amounts as reported).

**Known gaps**
- Acceptance 7 (Stripe test-mode walkthrough with the CLI), 8 (publish
  both policy versions), and 9 (deploy and repeat 1 and 2 on
  production in test mode): not yet run by the operator.
- Acceptance 1–5 were proven at the API layer by the backend suite and
  the page states by the frontend suite; the browser walkthrough of the
  same steps was not performed in the build session.
- Preflight on an open site now needs Stripe reachable (one
  `Price.retrieve`); a transient outage refuses a deploy, as 026's
  bucket-versioning check does. Coming-soon is unaffected.
- The webhook's completed-session handler makes one outbound Stripe
  call. If Stripe is unreachable at that moment the row stays
  `incomplete` until the next subscription event; no retry of our own.
- Stripe Tax on subscriptions is a note in OPERATIONS.md, not built.
- Out of scope, reported not built: monthly or other intervals; team or
  multi-seat plans; gifting; plan switching, trials, promo codes, any
  coupon but the per-account credit; automatic voiding or automatic
  cancellation on refund; any billing email of superCPE's own; a grace
  period for `past_due` (decided: none); Google sign-in (030);
  `customer.subscription.created` handling; automatic tax.
- pyflakes reports two pre-existing unused imports
  (`app/routers/checkout.py`, `app/models/enrollment.py`) untouched by
  this feature; oxlint's remaining warnings are all on untouched files.

## 030 — Sign in with Google
Shipped: 2026-09-12

**What changed**
- Task 0 (recon), answered before code was written:
  1. Password login sets the session in `backend/app/routers/auth.py`:
     `auth_service.authenticate` → `auth_service.open_session` (the
     random token whose sha256 is the `sessions` row) →
     `_set_session_cookie` (`supercpe_session`, HttpOnly, SameSite=Lax,
     Secure unless `DEV`, path `/`, max-age `SESSION_ABSOLUTE_HOURS`) →
     `_me` for the body. Google sign-in lives in the same router and
     calls the same three functions; nothing is copied.
  2. `deploy/Caddyfile` sets exactly one security header today:
     `Strict-Transport-Security`. There is no Content-Security-Policy,
     no Cross-Origin-Opener-Policy, no frame header, on the Caddyfile,
     the API, or `index.html`. Nothing must be added for Google's
     script, popup, or iframe to work, so **no header line was added**
     — the smallest change that works is none, and adding a CSP would
     be a feature of its own. The directives a future CSP would need
     are recorded in OPERATIONS.md "Google sign-in (030)". The one
     Caddyfile change is the rate limit: `path /api/v1/auth/login
     /api/v1/auth/google` in `zone login` (017's limiter is Caddy, not
     the backend).
  3. `accounts.password_hash` was NOT NULL; the migration makes it
     nullable. Passwords are verified in exactly two places, both in
     `backend/app/services/auth.py`: `authenticate` (login) and
     `change_password`. Both now go through one `password_matches`,
     which treats a null hash as a wrong password after spending one
     argon2 verification against the throwaway hash, so the refusal
     costs the same and reads the same (`LOGIN_FAILED`, or 009's "The
     current password is incorrect"). `registration.register` hashes
     but never verifies.
  4. **PyJWT with its cryptography extra, overruling the spec's
     default of google-auth.** `pip install --dry-run` in the venv:
     `google-auth` 2.58.0 would install three packages (google-auth,
     pyasn1, pyasn1-modules) and its `id_token.verify_oauth2_token`
     needs an HTTP transport object — `requests` (present here only
     through moto, a test dependency) or urllib3 — and refetches
     Google's certificates on every call with no cache. `PyJWT[crypto]`
     2.14.0 installs one package (cryptography is already present),
     `PyJWKClient` caches Google's JWKS with a lifespan and refetches on
     an unknown key id using stdlib urllib, and the issuer, audience,
     expiry, and required-claims checks are explicit in our thirty
     lines rather than inside a helper. Only
     `services/google_identity.py` imports it.
  5. 017 requires name (non-blank), email, and password; state of
     licensure is optional; there is no terms checkbox (the form says
     registering means agreeing to the registration policy). The name
     matters: `completions.py` snapshots `display_name` as the 9.01
     participant name. A Google-created account takes its name from
     the ID token's `name` claim, which Google's button always
     requests (`openid email profile`); the account is created complete
     with no extra step. If a token carries no `name`, `display_name`
     stays empty exactly as an admin-created account's can; no
     "finish your account" step was built (see Known gaps).
  6. vitest/jsdom tolerates the loader: an appended external `<script>`
     is inert (jsdom fetches no resources), so `onload` never fires and
     the promise stays pending. The mock is at the module boundary:
     tests `vi.mock` `src/auth/googleIdentity.js` to resolve a fake
     `{ initialize, renderButton }` and read the callback back out of
     `initialize`'s argument; one test drives the real loader and pins
     that two calls append one tag.
- Config: `GOOGLE_CLIENT_ID` (optional, alone, default unset) in
  `config.py` (`google_configured`), `.env.example`, and
  `deploy/env.production.example`; preflight prints a
  "configured / not configured" note either way, never a violation.
  Not in any all-or-nothing group, not a readiness finding.
- Data model: `accounts.google_sub` (nullable, unique, set once) and
  `accounts.password_hash` nullable; hand-written migration
  `e7c2a9f4b130_google_sign_in`.
- `backend/app/services/google_identity.py`: the boundary —
  `verify(credential) -> GoogleIdentity(sub, email, email_verified,
  name)` or `GoogleIdentityError`; RS256 against Google's JWKS,
  `iss` in Google's two values, `aud == GOOGLE_CLIENT_ID`, `exp`, and
  `sub`/`iat`/`aud`/`iss` required. Tests stub it as 018 stubs
  `stripe_gateway`.
- `auth_service.sign_in_with_google` (one function): verify; unverified
  email refused; account by `google_sub` → active participant signs
  in; else account by case-folded email → active participant not yet
  linked gets `google_sub` set (once) and `email_verified_at` if null,
  signs in; else a participant is created with email, `google_sub`,
  `email_verified_at = now`, `display_name` from the token, no
  password, `must_change_password` false. Every refusal raises the same
  `AuthenticationFailed(GOOGLE_SIGN_IN_FAILED)`.
- Routes, both behind `require_site_open_or_session`:
  `GET /api/v1/auth/google/config` → `{"client_id": "…" | null}`;
  `POST /api/v1/auth/google` `{"credential"}` → the password-login
  shape (`MeOut`) with the same cookie, or 401
  `{"detail": "Sign in with Google did not succeed"}`. `MeOut` gains
  `signin_methods` (derived: `["password"]`, `["google"]`, or both), so
  `/auth/me`, `/auth/login`, and `/auth/google` all carry it.
- Frontend: `src/auth/googleIdentity.js` (the one place the GIS
  `<script>` is written — once, lazily; never `index.html`),
  `src/components/GoogleSignIn/` (renders nothing unless
  `siteFace() === OPEN` and the config's client id is non-null; then an
  "or" divider and Google's rendered button, `ux_mode: "popup"`,
  `auto_select: false`, no One Tap; the callback POSTs the credential
  and hands the account to the page), mounted on `Login` (routes
  through the same `finishSignIn` as the password form, `from`
  redirect included) and `Register` (`signup_with` wording, then
  `roleHome`). `/account` gains a "Sign-in methods" card (Password /
  Google / Password and Google) and offers "Change your password" only
  when a password exists; a Google-only account reads "This account has
  no password; it signs in with Google."
- Tests: backend 523 → 540 (`tests/test_google_sign_in.py`, 15: the
  three outcomes, response shape identical to password login, linking
  once then matching by `sub` with a changed Google email creating no
  second row, an unverified registration verified by Google, eight
  refusal cases byte-identical with no row created or changed,
  `GOOGLE_CLIENT_ID` unset → null config and the constant 401 not 404,
  404 anonymously in coming-soon and answering with a session,
  password login and change-password on a no-password account, a
  password set later giving both methods, `google_sub` unique,
  `signin_methods` derived; plus two preflight note tests). The router
  walk and `INTENTIONALLY_PUBLIC` are untouched and green. Frontend
  104 → 122 (`Login.test.jsx` 6, `Register.test.jsx` 3,
  `GoogleSignIn.test.jsx` 4 through the real App: coming-soon landing,
  coming-soon `/login`, and `/admin/courses` at open never ask for the
  config or load GIS; `/login` at open loads it once;
  `googleIdentity.test.js` 2; `Account.test.jsx` +3 for the three
  `signin_methods` variants).
- Ops: OPERATIONS.md "Google sign-in (030)" (OAuth client creation,
  origins, no redirect URIs, the env value, the header note, the
  consent screen, Testing mode, the walkthrough, turning it off) and
  Opening day gains step 6 with both lines (client id deployed and
  walked; privacy policy decided); steps 6–10 became 7–11 and the two
  in-document references were updated.

**Standards touched**
- None. Identity verification is not a Standards requirement; 9.02's
  participant records are unchanged (one nullable column on the
  account row, and `password_hash` may now be null). COMPLIANCE.md is
  not changed: no locator's requirement or satisfaction moved, and the
  file keeps no "not touched" line to append to.

**Decisions**
- One constant refusal for every failed Google sign-in, distinct from
  the password constant: `"Sign in with Google did not succeed"`. A
  Google account holder for `x@y` gets that body whether `x@y` has no
  account, a deactivated one, an admin's, a reviewer's, one linked to a
  different Google account, or whether the token itself was bad or
  unverified — so the endpoint cannot be used to learn whether `x@y` is
  a superCPE account or what kind. The tests assert the bodies are
  byte-identical and that no row changed.
- An account already linked to a different `google_sub` is refused on
  the email branch rather than relinked: `google_sub` is set once.
- Google sign-in does not consult `locked_until` or `failed_logins`;
  those belong to the password door. It does refuse `is_active` false.
- The privacy-policy dependency is an operator decision, not a page:
  the consent screen stays in Testing mode (listed test accounts only)
  until a privacy policy exists somewhere; recorded in OPERATIONS.md and
  the opening-day checklist, not built.
- A session loaded from a pre-030 payload with no `signin_methods` is
  read by the account page as password-only.

**Known gaps**
- Acceptance 7 (production client id, deploy, repeat 1 and 2 on
  production with the consent screen in Testing mode): not yet run by
  the operator.
- Acceptance 1–5 were proven at the API layer by the backend suite and
  the page states by the frontend suite; the browser walkthrough with a
  real client id and Google's popup was not performed in the build
  session (no client id in `.env`). Two parts of it cannot run at all
  yet: acceptance 1's "the accounts admin list shows the row with
  `email_verified_at` set" — `AccountOut` and `/admin/accounts` do not
  expose `email_verified_at` for any account, so it is visible only in
  the database; and acceptance 4's "run the reset flow" — see next.
- **017a (password reset) does not exist.** The spec reads as if it
  does; ROADMAP.md records it as never built. Consequences: a
  Google-only account has no way to add a password today; the
  `/account` line "To add a password, use Forgot password" was not
  rendered (there is nothing to link) and reads "This account has no
  password; it signs in with Google." instead; and the test for "017a
  reset sets a password and password login then works" is stood in
  for by `test_a_password_set_later_makes_both_methods_work`, which
  stores what a reset would store. When 017a ships it must write
  `password_hash` through `auth_service._hasher` and nothing else
  changes here.
- No participant-facing way to set or correct `display_name` exists
  for any account type, Google-created or not; a token with no `name`
  claim leaves it empty until an admin edits it. A "finish your
  account" step was not built (Task 0.5).
- Out of scope, reported not built: redirect/code flow, refresh tokens,
  storing any Google token; Google sign-in for admin or reviewer roles
  or any role change by Google; unlinking or changing the linked
  Google account; One Tap, auto sign-in, Apple or Microsoft sign-in;
  waiting-list invitation (021) via Google; a privacy policy page; any
  change to 017's verification email or the constant-response bodies;
  a Content-Security-Policy for the site.
- pyflakes reports pre-existing unused imports on untouched files
  (`app/routers/checkout.py`, `app/models/enrollment.py`, and six test
  modules); oxlint's remaining warnings are all on untouched files.
- The working tree already carried the operator's uncommitted edits to
  CHANGELOG.md (027–029 entries), CLAUDE.md (rule 5), OPERATIONS.md
  (Stripe sandbox notes), and current-feature.md when this session
  began; they are not this feature's changes and were left as found.

## 030a — Google sign-in preview on a closed site
Shipped: 2026-09-13

**What changed**
- Task 0 (recon), answered before code was written:
  1. The gate was applied per route in `backend/app/routers/auth.py`:
     `dependencies=[Depends(require_site_open_or_session)]` on
     `google_config`, and the same ahead of `require_json` on
     `google_sign_in`. The router walk
     (`test_router_walk_closed_site_hides_everything_not_intentionally_public`
     in `tests/test_site.py`) requests every route anonymously while
     coming_soon and asserts 401 or 404 unless the route is in
     `INTENTIONALLY_PUBLIC`, and not-404 when it is — so a route that
     drops the gate without joining the list fails by name. The bare
     404 is `HTTPException(status_code=404, detail="Not found")`:
     status 404, body exactly `{"detail":"Not found"}` (FastAPI's
     default handler, no whitespace).
  2. The gate reads `site_service.get_site_mode(db)` — one
     `get_profile(db).site_mode` query — callable from any handler with
     the request's `db`. `cli.stored_site_mode()` is the CLI's wrapper
     that opens its own session and tolerates a missing table; it is
     not for routes. Reused: the gate's own predicate, factored out of
     the dependency as `site_open_or_session(request, db)` in
     `app/auth.py`, alongside a `site_gate_refusal()` factory so the
     handler raises the dependency's exception, not one of its own.
  3. `CORS_ORIGINS` is the one comma-separated setting: stored as a
     string, parsed by the `cors_origins_list` property (strip, drop
     empties). `GOOGLE_PREVIEW_EMAILS` copies it as
     `google_preview_email_set` (a frozenset, lower-cased the way
     `accounts.email` is stored). 012's validator has no notion of a
     note — `boot_violations` returns only refusals; notes existed only
     as `print("note: …")` lines inside `cli.preflight`. So config.py
     gains `boot_notes(settings) -> list[str]`, which preflight prints
     behind `note:`; boot ignores it.
  4. `AccountOut` carried id, email, role, display_name, is_active,
     must_change_password, created_at, deactivated_at, last_sign_in,
     open_sessions; built by `_account_out` in
     `routers/admin_accounts.py`; rendered by
     `frontend/src/pages/AdminAccounts/AdminAccounts.jsx` (Email, Role,
     Active, Last sign-in, Open sessions, actions). `Account.
     email_verified_at` exists under that name. Two fields, two
     columns, one test each side — in scope, built.
  5. `GoogleSignIn.test.jsx` "the sign-in page while coming-soon asks
     nothing of Google" mounts the real App at `/login` with the site
     coming_soon and no session, and asserts `getGoogleConfig` was not
     called, `loadGoogleIdentity` was not called, and no GIS `<script>`
     tag exists. The reversal is that first assertion
     (`not.toHaveBeenCalled()` → `toHaveBeenCalledTimes(1)`), split
     into the 404 case (still no GIS, no tag, no button) and the
     answering case (GIS once). `Login.test.jsx` had a parallel "asks
     nothing of Google while coming-soon" test, reversed the same way.
- Config: `GOOGLE_PREVIEW_EMAILS` (optional, default empty) in
  `config.py`, `.env.example`, `deploy/env.production.example`. Not in
  any all-or-nothing group, not a readiness finding, never part of the
  open gate. `boot_notes`: "GOOGLE_PREVIEW_EMAILS is set but
  GOOGLE_CLIENT_ID is not; it has no effect." Preflight prints, in both
  modes, "note: GOOGLE_PREVIEW_EMAILS lists N address(es); Google
  sign-in on /login completes for them while the site is coming-soon."
  (pluralised) or "note: GOOGLE_PREVIEW_EMAILS is not set."; on an open
  site with the list set it adds "The site is open; the list is inert —
  unset it (Opening day step 6)." Never a violation.
- `.env.example` also gains `GOOGLE_CLIENT_ID`: the 030 entry says it
  was added there, but the committed file never carried it
  (`deploy/env.production.example` did). Corrected here, since the new
  variable's comment refers to it.
- Backend gate: both Google routes drop `require_site_open_or_session`
  for `require_site_open_or_session_or_preview_list` (in the auth
  router): passes when the list is non-empty, otherwise exactly the 009
  gate — and it still runs before the body is parsed, so with the list
  empty an anonymous malformed request on a closed site gets the 404 it
  got in 030, never a 422. `google_config` is otherwise unchanged (the
  dependency is the whole decision). `google_sign_in`: when the request
  passes neither the open check nor a session, `_preview_listed`
  verifies the token at the boundary and requires `email_verified` and
  a lower-cased email on the list; anything else raises
  `site_gate_refusal()`. Only then does the existing
  `sign_in_with_google` run, untouched. Both routes joined
  `INTENTIONALLY_PUBLIC` (exactly two additions) with the argument in
  the comment; the walk is now parametrised to run with the list unset
  (the two routes must be gated like everything else) and with an
  address listed (they must answer).
- `AccountOut` gains `email_verified_at` and `signin_methods` (the
  latter through `auth_service.signin_methods`, the same helper `MeOut`
  uses — not copied). `/admin/accounts` shows **Verified** (date or
  "—") and **Sign-in** (Password / Google / Password and Google,
  through the account page's `signinMethodsLabel`); no filter, no edit.
- Frontend: `GoogleSignIn` no longer reads the site face; it asks for
  the config on mount and renders on a non-null client id. GIS loading
  is unchanged (once, lazily, only after a non-null config). `Login`
  mounts it as before, in both modes; `Register` is untouched and
  unreachable while closed (behind `SiteGate`). A 404 leaves the page
  as it was; the constant 401 shows 030's one generic line.
- Tests: backend 540 → 557 (`tests/test_google_preview.py`, 9: empty
  list → both routes and a malformed body give the gate's 404 byte-
  identical to `GET /api/v1/courses`' and nothing is written; a listed
  address signs in while coming-soon with a body byte-identical to the
  same token's at open; case-folding of a padded mixed-case env value
  against an upper-cased token; six unlisted outcomes (new address,
  existing unlisted account, unverified, expired, wrong audience, bad
  token) all the gate's 404 with `sign_in_with_google` stubbed to fail
  the test if reached and no row or session changed; listed admin,
  reviewer, and deactivated accounts get the constant 401 not 404; at
  open the list changes no answer across five cases; with a session in
  coming-soon both routes answer regardless of the list; the two routes
  are the only preview routes and are in `INTENTIONALLY_PUBLIC`; the
  shared derivation. `test_site.py` router walk ×2; `test_preflight.py`
  +4 (unset, set while coming-soon with the count, set while open with
  the inert line, set without a client id); `test_config.py` +2
  (parsing, never a violation); `test_auth.py` +1 (`AccountOut` fields
  for the admin-created, Google-only, both, and unverified rows, still
  admin-only). Frontend 122 → 127 (`GoogleSignIn.test.jsx` 4 → 5, the
  reversal split in two; `Login.test.jsx` 6 → 7, the coming-soon 404
  case and a listed-address success routing to `/my/courses` with no
  register link; `AdminAccounts.test.jsx` new, 3).
- Ops: OPERATIONS.md "Google sign-in (030)" gains "Preview before open
  (030a)" with a placeholder line for the production run; Opening day
  step 6 gains a third line, **unset `GOOGLE_PREVIEW_EMAILS`**.

**Standards touched**
- None. No paragraph was read for this feature and none is cited: 9.02
  participant records are unchanged (no model change, no migration),
  and no locator's requirement or satisfaction moved. COMPLIANCE.md is
  not changed.

**Decisions**
- **An allowlist, not an exemption.** 026 exempted the Stripe webhook
  from the gate because its answer discloses nothing the gate protects.
  The Google sign-in route cannot make that argument on its own — a
  successful answer is a session — so it is not exempted; it is given
  one door, and the door is the operator's list. The 009 property in
  this feature's words: a closed site must not tell an anonymous
  visitor what is behind it. With the list empty, both routes are the
  gate's 404 and nothing here exists. With the list set, the config
  route says only that a Google client exists — a client id is in every
  page that renders the button, so it is public by construction and
  names no course, price, credit figure, or account — and the sign-in
  route says nothing at all to anyone whose Google-verified email the
  operator did not type into the env file: a bad token, an unverified
  address, and an unlisted address get the same bytes a missing route
  gets, and no row is created, linked, or changed before the check
  passes. A listed address then sees exactly what an open site would
  show it, refusals included (an admin's listed address gets the
  constant 401, as at open). Google's Testing-mode test-user list also
  limits who can finish the popup, but that is the operator's promise;
  the allowlist is what the tests assert.
- **The token is verified twice on the preview path**: once in
  `_preview_listed` for the allowlist, once inside
  `sign_in_with_google`. Accepted: the second check costs a signature
  verification against PyJWKClient's cached keys, and the alternative —
  threading a pre-verified identity into the service — would fork the
  one function 030 built to have no forks.
- **The gate dependency stays, in a variant, rather than moving the
  whole decision into the handlers.** FastAPI parses the body before
  the handler runs, so a handler-only 404 would have let an anonymous
  malformed POST on a closed site with the list unset answer 422 where
  030 answered 404. `require_site_open_or_session_or_preview_list`
  runs first and keeps the empty-list case byte-identical; only with a
  non-empty list does a malformed body reach validation — and in that
  state the config route already says a Google client exists.
- **Case-folding is `str.lower()`**, matching how `accounts.email` is
  stored and compared (`get_account_by_email`), rather than
  `str.casefold()`, so the env value, the token's email, and the stored
  row all fold the same way.
- **One frontend assertion reversed, deliberately.** 030 asserted that
  the coming-soon `/login` never asks for the Google config; the
  component made that decision from the site face. 030a moves the
  decision to the server, which alone knows the list, so the page asks
  once and the server's 404 is the "no". The property that mattered —
  the closed site never loads Google's script unless a client id was
  answered — is kept and asserted in both the 404 and the answering
  case. The landing page and `/admin/courses` still never ask.
- The preflight count is pluralised ("1 address", "2 addresses")
  rather than printed as the spec's template "N address(es)".

**Known gaps**
- Acceptance 6 (production: set `GOOGLE_CLIENT_ID` and
  `GOOGLE_PREVIEW_EMAILS`, deploy, repeat 2 and 3 on supercpe.com, then
  030's acceptance 2, and log the run in OPERATIONS.md, closing 030's
  Acceptance 7 early): not yet run by the operator. The consent-screen
  Test-user setup is the operator's.
- Acceptance 1–5 were proven at the API layer by the backend suite and
  the page states by the frontend suite; the browser walkthrough with a
  real client id and Google's popup (acceptance 2 and 3 locally) was not
  performed in the build session.
- A non-JSON body (not merely a malformed JSON object) on
  `POST /auth/google` gets FastAPI's 422 from JSON decoding before any
  dependency runs, on a closed site in either state. This was 030's
  behavior too and is unchanged; it is noted, not fixed.
- 017a (password reset) is still unbuilt; a Google-only account still
  has no way to add a password.
- `Register` has no preview by design: it is behind `SiteGate` and
  renders only at open, so the closed site never gains a sign-up
  surface.
- Out of scope, reported not built: password login or 017
  self-registration on a closed site; any preview for `/register`, the
  catalog, or course pages; a general preview mode or staff-preview
  cookie; any change to 026's open gate or to the constant-response or
  404 bodies.
- pyflakes still reports the pre-existing unused imports 030 listed
  (`app/routers/checkout.py`, `app/models/enrollment.py`, six test
  modules); oxlint's 12 remaining warnings are all on untouched files.

## 031 — Free seeking on the video player, up to the next unanswered review question
Shipped: 2026-09-13

**What changed**
- Task 0 (recon), answered before code was written:
  1. **Review points.** `reviewPoints` in
     `frontend/src/components/Player/Player.jsx`: a `useMemo` over
     `lesson.questions`, each mapped to
     `{ time: lesson.blocks[after_block - 1].end_seconds, question }`,
     sorted by time. Unchanged.
  2. **Answered state.** The enrollment play payload (`play_lesson` in
     `backend/app/routers/my.py`, `MyPlayLesson`) carried no per-question
     `answered`; the reader payload did — `ReaderQuestionOut.answered`
     (`backend/app/schemas/reader.py`), set in `reader.build` from
     `answered_keys`, which `read_lesson` in `my.py` derives as the
     question keys whose `Question.id` is in
     `enrollments.answers_by_question(db, enrollment)` (one
     `review_answers` row per (enrollment, question), re-answer updates
     the row). The video payload now uses the same dict.
  3. **Preview identity.** Preview review answers are not persisted
     anywhere: `grade_review` in `backend/app/routers/player.py` grades
     and returns; 007's `X-Preview-Id` keys only preview *assessment*
     attempts (`routers/assessment.py`). So the preview payload says
     `answered: false` on every load and the player tracks answers in
     component state for the session — which is what happened before.
     The enrollment path uses the `review_answers` record.
  4. **`furthest_seconds`.** Readers of the column: `record_progress`
     (writer, monotonic) and `progress()` in
     `backend/app/services/enrollments.py`; `play_lesson` and
     `put_progress` in `routers/my.py`; `MyLessonProgress`,
     `MyPlayLesson`, `ProgressUpdate`, `ProgressOut` in
     `schemas/enrollment.py`; the participant instructions text
     (`services/instructions.py`); `MyCourse.jsx` (the "m:ss / m:ss"
     line) and `MyLesson.jsx` (`initialFurthestSeconds`) in the
     frontend. Readers of the player's `furthest` state: none — only
     `furthestRef` was read. **`lesson_done` (enrollments.py:423) does
     derive a video lesson's `done` from `furthest_seconds` reaching
     `duration_seconds - WATCHED_TOLERANCE_SECONDS`; a text lesson's
     from `review_answered == review_total`.** Its docstring says it is
     display only: nothing that gates the assessment, records a
     completion, or reaches a certificate or the audit bundle reads it
     (the gate is `assessment_available`). Reported, not changed — see
     Known gaps for what the ceiling does to its meaning.
  5. **The pinned refusal.** `Player.test.jsx` › "Player seeking (027)"
     › "still refuses a forward seek past the furthest point watched".
     Replaced by the eight seeking tests below, not deleted silently.
  6. **The unused `furthest` state variable.** Gone as a consequence:
     `furthest`/`setFurthest` were never read (only `furthestRef` was),
     and nothing in the new player renders from it. oxlint's warning
     count drops from 12 to 11.
- Backend: `PlayQuestion` gains `answered: bool`
  (`backend/app/schemas/player.py`). The enrollment route sets it from
  `answers_by_question` — the reader's derivation, not a copy of it —
  and the preview route sets `False` with the reason in a comment. No
  migration. `walk_asserting_no_answer_key` still passes over both
  payloads: `answered` is a fact about the participant's own record,
  never the key.
- Player (`Player.jsx`): `answeredKeys` (a Set seeded from the payload,
  grown when a grade resolves), `ceilingPoint` (the earliest review
  point not in it), `ceiling` (its time, else the media duration).
  `seekTo` clamps to `[0, ceiling]` — bar click, arrow keys, Rewind, and
  the new Forward all go through it. `handleSeeked` undoes a seek past
  the ceiling to the ceiling and, when a seek lands on the ceiling (within
  `SEEK_TOLERANCE_SECONDS`), snaps to it and asks its question through
  the same `askQuestions(points)` the playback crossing detector now
  calls — pause, queue the rest behind Continue, open the first. The
  in-flight clamp stays on `seeked` (006's reason). Resume on
  `loadedmetadata` seeks to `min(furthest, ceiling)`, so a reload past an
  unanswered point lands on the point and asks. "Forward 15 s"
  (`FORWARD_SECONDS`, beside `REWIND_SECONDS`) sits beside Rewind. Ticks
  at answered review points take `tickAnswered` (the existing
  `--color-success` token) and the title "Review question (answered)";
  unanswered ticks are unchanged. `furthest_seconds` is still advanced
  on `timeupdate` and reported as before; it gates nothing.
- Tests: backend 557 → 559 (`test_player.py`: preview payload marks every
  question unanswered even after a preview grade; enrollment payload
  flips exactly the answered question after one `review_answers` row,
  a wrong answer counting as answered). Frontend 127 → 133
  (`Player.test.jsx` seeking: backward seek and Rewind kept; forward seek
  past the first unanswered point clamps to it and asks; a forward seek
  within the ceiling past `furthest` is honoured and ArrowRight landing on
  the ceiling asks; Forward 15 s from 10 s lands on 25 s and keeps going,
  from 35 s lands on 40 s and asks; after answering the first question a
  seek to 60 s is honoured and a seek to 110 s clamps at 80 s with the
  ticks reading answered/unanswered; every question answered on load →
  a seek to 119 s honoured; resume with `furthest_seconds` 100 and the
  second question unanswered lands on 80 s and asks; a wrong answer's
  "Re-watch this section" seeks to the block start, resumes, and the
  ceiling has moved on; the three 027 end-panel tests kept). `conftest.py`
  now pins `google_client_id` and `google_preview_emails` to empty for the
  suite — see Known gaps.
- Docs: COMPLIANCE.md Notes edited on the 006 rows for 5.01.2, 5.01.2.1,
  and 6.01 (no new rows) and on the 023 5.01.2.1 row, whose "The
  video-only player keeps its lock" is now qualified.
  `docs/decisions/2026-09-13-video-seek-ceiling.md` records the decision
  alongside 023's text-first file.

**Standards touched**
- 5.01.2.1 — printed page 9 (the chart runs onto page 10). Placement is
  unchanged; the ceiling is what guarantees each placed question is
  presented before playback continues past it, which is all the
  paragraph asks of the player. COMPLIANCE.md 5.01.2 and 5.01.2.1 Notes
  updated.
- 5.01.2.2 — printed page 10. Read to confirm nothing about feedback
  moves; nothing does. COMPLIANCE.md not changed for it.
- 6.01 — printed page 10. Completion verification is the review-answer
  record plus the qualified assessment; playback position never was a
  completion signal and is not one now. COMPLIANCE.md 6.01 Notes
  updated.
- 7.02.6–7.02.7 — not re-read for this feature (the spec's summary was
  relied on): Method 2 credit is computed from measured inputs, not from
  how a participant moves through the media; nothing here touches
  credit.

**Decisions**
- **Reversal of 006's Decision** "Forward-seek prevention is a sponsor
  design choice, not a Standards requirement (5.01.2.1 sets no such
  rule), and is enforced only in the player", and of the 023 resolution
  in `docs/decisions/2026-09-01-text-first.md` and ROADMAP.md ("relaxed
  for supplemental clips, kept for the video-only player"). This is the
  counterpart of 023's reader-clip decision, made for the video-only
  player: the sponsor wants forward and backward controls and keeps the
  one thing the lock protected — no placed review question can be
  skipped. Asked for by the spec (CLAUDE.md rule 7).
- **The ceiling is the earliest unanswered review point, not the
  furthest watched.** Seeks never ask a question except when they land
  on the ceiling; playback crossing any review point still asks it,
  answered or not (006's behavior, and what the wrong-answer re-watch
  flow relies on). The spec's Out of scope described "today's behavior"
  as playing through an answered point without re-asking; the code has
  re-asked on every crossing since 006, and that was left as it is —
  changing it is out of scope by the spec's own list.
- **A seek that lands on the ceiling asks through the playback path**:
  one `askQuestions(points)` serves the crossing detector and the seeked
  handler, so there is one way a question opens.
- **Answered is marked when the grade resolves**, not on Continue: on
  the enrollment path that is the moment the `review_answers` row
  exists; in the preview, state is all there is.
- **`answered` is required on `PlayQuestion`, not defaulted**, so both
  serializers have to say it; the player treats a missing flag as false
  for any older payload.
- **Ticks got the answered variant** with the existing success token —
  one CSS rule, not design work.
- **`furthest_seconds` still advances only on `timeupdate`**, so a
  forward seek followed by nothing does not move the resume point;
  playing after it does.

**Known gaps**
- **Lesson `done` for a video lesson depends on `furthest_seconds`**
  (`lesson_done`, Task 0.4). This feature did not change that derivation
  — it is out of scope — but the ceiling changes what it means: once
  every review question in a video lesson is answered, a participant can
  seek to the end, the next `timeupdate` advances `furthest_seconds`
  there, and the lesson reads "done" on the course page and in the
  next-step derivation without having been played through. Before, only
  playback (or the 027 reload-past-a-question case) could get there.
  `done` is display and navigation only; the assessment gate,
  completion, certificate, and audit bundle never read it. Whether a
  video lesson's `done` should read from the review record, as a text
  lesson's already does, is the operator's decision; recorded in the
  decision file. Report, not build.
- Acceptance 4 (the walkthrough on production with the ATO video lesson
  after deploy): not yet run by the operator. Acceptance 2 and 3 (the
  local browser walkthrough with a real video in the admin preview and
  an enrollment) were not performed in the build session; the same
  sequences are proven in `Player.test.jsx` against a jsdom media
  element with the seek events fired by hand.
- 027's end panel is unchanged: "Answer the review questions" still
  re-asks every question in the lesson, though the payload now carries
  the flag that would let it ask only the unanswered ones. With the
  ceiling the panel's remaining-questions branch is reachable only when
  a reload mid-question resumed past a review point, as 027 documents.
- `conftest.py` did not pin the Google settings, so the suite's shape
  depended on the developer's `.env`: with `GOOGLE_PREVIEW_EMAILS` set
  locally (as the operator set it after 030a), three 030/030a tests
  failed. Pinned here, alongside the email and Stripe pins. A 030a gap
  closed in passing, not a 031 change.
- ROADMAP.md's 023 note still reads "kept for the video-only player";
  it is a historical note, not a rule, and was not edited.
- Out of scope, reported not built: reader clips, the assessment,
  grading or feedback wording, `review_answers` or `lesson_progress`
  changes, skip-to-next-point, playback speed, captions, a player
  library, placement rules, re-ask behavior on seek-back, ingest, credit,
  readiness, video-tool.
- pyflakes still reports the pre-existing unused imports 030 listed;
  oxlint's 11 remaining warnings are all on untouched files.

## 032 — Certificate redesign: render from an HTML template
Shipped: 2026-09-13

**Task 0 answers**
1. *Current library.* `render` used fpdf2 (010/011). Its only callers
   were `services/certificates.py` and the `positioned_runs` ruler in
   `tests/test_certificates.py` (fpdf2 as a width-measuring stand-in for
   the renderer's own metrics). The audit bundle never rendered; it
   copies the stored PDF. fpdf2 is removed with this feature; the ruler
   now measures with fontTools, which WeasyPrint depends on. Pillow,
   which the identity script needs, stays as a WeasyPrint dependency
   the way it was an fpdf2 one.
2. *What the tests pin.* `test_certificates.py`: every 9.01 item as
   text (`test_certificate_text_carries_every_item`), the non-Latin
   name and DejaVu-only embedded fonts, re-render text identity, item 8
   printing when the snapshot carries it, a state registration line,
   the admin render refusal and the late legal name not printing, the
   participant download, and the 023c D1 placement test (one page,
   letter media box, every run's x/y/end-x inside the 20 mm margins,
   the wrapped title's two halves each in one run, and the exact
   labelled lines `Completion date: …`, `Location: Not applicable
   (self study)`, `Type of learning program: Self study`, `CPE credit:
   0.4 in Accounting`, `Certificate number: …`, the token and the
   verify wording). `test_audit_bundle.py`: the stored PDF and its
   snapshot JSON are in the zip (no text assertion on the PDF).
   `test_certificate_delivery.py`: the attachment name and that the
   render happened. All pass unchanged except `positioned_runs`, whose
   measurement was swapped (WeasyPrint draws in CSS px under a page
   transform; the helper composes `cm` and `tm` and sums advance
   widths from the vendored faces).
3. *Palette and mark.* `generate_identity.py` reads
   `frontend/src/styles/global.css` with a regex per `--color-*` token
   and writes the favicon.ico, touch icon, manifest icons, `og.png`,
   and manifest. The favicon SVG is **not** a monogram any more: 024
   swapped in a Flaticon graphic whose license permits favicon use and
   forbids logo use — it may not appear on a certificate. So the mark
   is drawn as code: the script gained one step (`write_brand`) that
   writes `backend/app/assets/brand/palette.py` (the tokens as a dict)
   and `backend/app/assets/brand/monogram.svg` ("sC" glyph outlines
   lifted from DejaVu Sans Bold with fontTools, on a rounded accent
   square — pure paths, no `<text>`, no font needed where it is drawn).
   Both are committed, because the backend never imports from
   `frontend/` and the image build copies `backend/` only; a test
   re-runs the two functions and refuses a committed file that differs.
4. *Renderer.* WeasyPrint 70.0 on `python:3.12-slim`. ffmpeg already
   pulls the Pango, HarfBuzz, and fontconfig libraries into the image;
   the only new apt package is `libharfbuzz-subset0` (one package,
   under a megabyte). The apt step took 21 s and the pip step 20 s in
   the build run; the built image is 1.55 GB, of which the WeasyPrint
   wheels (pydyf, tinycss2, cssselect2, tinyhtml5, pyphen, brotli,
   zopfli, fonttools) are a few megabytes. No fallback needed; nothing
   is fetched at render time (the fetcher admits only data: URIs and
   files under `app/assets/`).
5. *Fonts.* The three vendored DejaVu files are declared with
   `@font-face` under the family name `DejaVuSans` (no space — so a
   system "DejaVu Sans" can never be chosen over them, and because
   WeasyPrint names the embedded font after the family, which the
   011 test asserts). Kerning is off in the stylesheet: a kerned "Ty"
   extracts as "T ype", and every item must extract as written. No
   second display face: DejaVu Sans only, as the spec's default.
6. *Snapshot keys read.* `sponsor_name`, `sponsor_legal_name`,
   `participant_name`, `participant_email`, `course_title`,
   `course_code`, `completed_at`, `program_type`, `credit`,
   `field_of_study`, `time_statement`, `national_registry_id`,
   `state_registrations`, `other_statements`, `developed_by`,
   `reviewed_by`, `certificate_number`, `verification_token`. Not
   read: `location` (item 5 prints the fixed self-study line),
   `knowledge_level`, `package_versions`, `passing_pct`, `score_pct`,
   `recommended_credit_basis`, `snapshot_version`. The template
   context is built from exactly that set (`_context`), plus the
   palette and the mark.

**What changed**
- `render(snapshot, logo=None)` fills `backend/app/templates/
  certificate.html` with Jinja2 and lays it out with WeasyPrint;
  `certificate.css` beside it holds the whole look. One framed page in
  the site's palette: the mark top centre, "Certificate of Completion"
  over the sponsor name, the participant's name as the focal point,
  the course title, the credit award set off in a bordered block with
  the time statement beneath it, the completion date, location, and
  program type lines, the sponsor block ("Authorized by <legal name>"
  over a rule, then item 8 when present, item 9 as held, item 11 as
  stored, developer and reviewer), and a footer band with the
  certificate number and the 019 verify line. Every 9.01 item is one
  whole line in one element so it extracts as one run. The frame is a
  fixed-height box with overflow clipped, so the document is one page
  whatever the snapshot holds. What shipped: `docs/certificate-sample.png`.
- `sponsor_profile.logo_path` (nullable, migration `a3f9c2e17b54`),
  `PUT /api/v1/admin/sponsor/logo` (multipart PNG or SVG, sniffed from
  the bytes, `LOGO_MAX_BYTES` cap, stored at `sponsor/logo.<ext>` via
  the existing storage service) and `DELETE …/logo` (back to the
  monogram; the object stays). `ensure_rendered` passes
  `sponsor.load_logo(db, storage)` into `render`; the snapshot is
  untouched and `render` with the dict alone still works (pinned).
- `GET /api/v1/admin/sponsor/certificate-preview.pdf`: a sample from
  `certificates.sample_snapshot` (fixed fake participant and course,
  today's date, the sponsor's facts as they stand, item 8 only when
  `may_claim_registry`, the same keys as a real snapshot — pinned)
  rendered on the fly and returned inline. No completion row, no
  storage object, nothing logged.
- `/admin/sponsor` gained a "Certificate" card: logo upload, clear,
  and a "Preview certificate" link that opens the PDF in a new tab.
- Boot, preflight, and `/health` check the renderer the way they check
  ffprobe: `ensure_renderer_available` lays out a trivial page;
  `/health` reports `renderer` (smoke-rendered once per process) and
  it contributes to the 503 like the others. `deploy/Dockerfile`
  installs `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`.
- Tests: backend 559 → 579 (`test_certificates.py`: toolchain renders
  a minimal page; snapshot-only render; item 8 absent prints neither
  the ID nor the words, present prints from the dict alone; item 9
  empty prints nothing, two registrations print; forty statements stay
  on one page; the monogram is the mark and leaves no raster image;
  an uploaded PNG is embedded at its pixel size; the fetcher serves a
  vendored font and refuses http, https, and a file outside
  `app/assets/`; the committed palette equals global.css's tokens; the
  committed palette and monogram equal what the identity script
  writes and the monogram carries no text, image, or href; the sample
  snapshot has exactly the real snapshot's keys; the preview is
  admin-only, returns inline PDF, stores nothing, respects
  `may_claim_registry` and prints registrations; a logo shows in the
  preview and the next real certificate, clearing it returns the
  monogram, and the stored PDF's bytes do not change.
  `test_sponsor.py`: PNG upload and clear, SVG upload, three
  non-images refused, oversize refused. `test_health.py`: `renderer`
  ok.) Frontend 133 → 137 (`AdminSponsor.test.jsx`: the preview link's
  href and target, upload calls the logo route with the chosen file
  and shows the stored key, clear calls the delete route and returns
  to the monogram wording, a 422 is shown).
- Docs: COMPLIANCE.md Notes edited on the 003/010 rows for 9.01 items
  1/8/9/10/11, 9.01.1, and 9.02 (no new rows). OPERATIONS.md gained
  "Certificate look (032)" and a `renderer: error` line under "When
  /health goes red".

**Standards touched**
- 9.01 — printed page 21. The eleven items, read again against the
  template: nothing added, dropped, or reworded; item 5 still prints
  "Not applicable (self study)", item 8 only from the snapshot.
  COMPLIANCE.md Notes updated.
- 9.01.1 — printed pages 21–22. The awarding entity is the "Authorized
  by" line, from `sponsor_legal_name` in the snapshot. COMPLIANCE.md
  Notes updated.
- 9.02 / 9.02.2 — printed page 22. The stored PDF is the retained
  record and is never re-rendered; the new look applies from the next
  render on. COMPLIANCE.md Notes updated.

**Decisions**
- **HTML-template rendering** (WeasyPrint, Jinja2) replaces the
  primitive-by-primitive drawing of 010. Layout is CSS beside the
  template; the palette is the site's own through a generated module.
- **The logo is presentation, not a snapshot fact.** It is an optional
  argument to `render`, read from the profile at render time, never
  frozen — re-rendering a stored certificate is not a thing this
  system does, so there is nothing to freeze.
- **No re-render of stored PDFs.** Certificates issued before 032 keep
  the 010 layout; the record is what was handed to the participant.
- **The monogram is drawn as code, not taken from the favicon.** 024's
  Flaticon icon may not be a logo; the "sC" mark is DejaVu Bold
  outlines on an accent square, generated by the identity script and
  committed with the palette. Palette sync mechanism: the script is
  the one writer of `palette.py` and `monogram.svg`, and
  `test_committed_brand_assets_are_what_the_identity_script_writes`
  refuses a drift.
- **Font family declared as `DejaVuSans`, kerning off** — for the
  011 font assertion and for text extraction that reads as written.
- **The sample snapshot lives beside `render`, not in `create`.**
  `create` is out of scope; the sample dict is a second copy of the
  key set, held equal by test.
- **Clearing a logo leaves the object in storage.** Nothing at the
  storage boundary deletes; the next upload of the same type
  overwrites it. Presentation, so no retention question either way.
- **Wording of the connective lines** ("This certifies that", "has
  successfully completed the qualified assessment for") follows the
  spec's layout; every 9.01 item and the verify line are verbatim.

**Known gaps**
- Acceptance 3 (browser: preview from `/admin/sponsor`, upload a logo,
  preview again, clear it) and 4 (complete the ATO course locally and
  compare the emailed and downloaded PDFs to the preview) were not
  performed in a browser in the build session; the same sequences are
  proven in `test_certificates.py` (preview, upload, preview, clear,
  and a real completion's download carrying the logo) and
  `test_certificate_delivery.py` (the attachment is the rendered PDF).
  Acceptance 5 (deploy, preview on production, a production
  completion's email through Resend with the new PDF): not yet run by
  the operator.
- Acceptance 2: `docker build` succeeded and `python -m app.cli
  preflight` passed inside the image against the local database
  (Stripe and Google settings blanked for the run, so nothing touched
  the network); a smoke render inside the image produced a PDF.
- The Docker image was not compared byte-for-byte against the
  previous build; the apt simulation shows one new package, and the
  Python additions are a few megabytes.
- The heading's letter-spacing is not counted by the placement test's
  width measurement (advance widths only); the line is centred and
  well inside the margins, so the check is loose by a few dozen points
  on that one line only.
- `test_no_new_route_carries_a_course_fact` (029) failed once in the
  final run and passed on three re-runs: it asserts the course's
  credit "0.4" is absent from response bodies, and a timestamp ending
  in `…30.428536Z` contained it. Pre-existing, time-dependent, not
  touched here. Report, not build.
- Local development now needs Pango (`brew install pango`); recorded
  in OPERATIONS.md.
- Out of scope, reported not built: snapshot contents, `create`,
  delivery, the verification page, the audit bundle's file set, any
  re-render or backfill, the Registry logo, multi-page or per-course
  templates, a second display face, signature images or signer names.
- pyflakes still reports the pre-existing unused imports 030 listed;
  oxlint's 11 remaining warnings are all on untouched files.

## 033 — Brand assets: one source, used everywhere
Shipped: 2026-09-13

The spec was numbered 032 and said it superseded "the earlier 032 draft
(certificate-only, 'sC' monogram for now)". That draft had already
shipped as the 032 entry above (the WeasyPrint template, the admin
preview, the sponsor logo upload, the generated monogram), so this
entry is 033 and builds on 032 rather than replacing it. Nothing in the
032 entry is edited; what 033 reverses is named under Decisions.

**Recon answers**
- `brand/` existed with six PNG/ICO files from Dane and no SVG, no
  palette file, no typeface: `supercpe-logo.png` (2172×724, the primary
  horizontal logo), `supercpe-icon.png` (1338×1338, the square mark),
  `favicon.ico` (16/32/48), `favicon-16x16.png`, `favicon-32x32.png`,
  `apple-touch-icon.png` (180). Both required roles are present; the
  palette was sampled from the artwork and recorded in `brand/README.md`.
- The certificate renderer was already WeasyPrint (032); Task 5 here is
  the mark, the seal, the palette, the file: fetcher, determinism, and
  the new tests — not a second renderer. `deploy/Dockerfile` and
  `requirements.txt` are untouched: no new dependency.
- The landing page has had no paragraphs, no policies footer, no
  Registry block, and no `/api/v1/landing` read since 024 (a commit
  without a changelog entry; its rule is in `COMPLIANCE.md`'s 8.01
  rows and the CLAUDE.md house rule "nothing rendered while coming-soon
  names a course … or 'National Registry'"). The spec's Task 4
  structure and its "Registry block renders when true" test describe
  015's page, not the page as it stands. 024 is kept: the page is the
  logo, "Coming Soon", and the form. Open question 1 is therefore moot
  — there is no ASC 842 sentence to replace, and the ComingSoon test
  still asserts the word "course" is absent.
- The open-mode root: `SiteGate` renders its children at `open`, so `/`
  is the catalog. Left alone.
- The spec's locator `frontend/src/favicon.svg` did not exist; the
  Flaticon SVG lived at `frontend/public/favicon.svg`. Deleted.
- `sponsor_profile.logo_path` (032) exists and stays as an override;
  see Decisions.

**What changed**
- `brand/README.md`: every file mapped to a role, source formats and
  dimensions, the sampled palette with the contrast arithmetic, and the
  ownership line ("Assets created by Dane for superCPE, LLC. Owned
  outright; no third-party license.").
- `frontend/scripts/sync_brand.py` replaces `generate_identity.py`
  (deleted with its monogram and DejaVu-drawn OG code). It derives
  fourteen files from `brand/`, `site.config.json`, and `global.css`:
  the four favicon files copied verbatim, `icon-192.png` and
  `icon-512.png` (the mark on opaque white, inset to 64% so a maskable
  crop keeps it whole; the manifest declares `any maskable`),
  `logo.png` (800×251, the artwork cropped to its alpha box), `og.png`
  (1200×630: the logo and "Coming Soon" from `site.config.json`,
  nothing else), `site.webmanifest`, the hashed-pipeline copies
  `frontend/src/assets/brand/logo.png` and `mark.png` (128), and the
  backend's `backend/app/assets/brand/logo.png` (the same bytes as the
  public one), `mark.png` (512, the seal), and `palette.py`. Every
  output is a pure function of the inputs; `--check` compares bytes
  and exits 1 naming stale files. Pillow only — no `cairosvg`, because
  every source is raster. `monogram.svg` is deleted.
- `global.css`: `--color-brand-blue #006afc`, `--color-brand-navy
  #012c6b`, `--color-brand-teal #01b6af` (the artwork's colours, for
  marks, rules, and fills), `--color-accent #0066f4` (text and links),
  `--color-bg #f5f7fb`, `--color-text #14213d`, `--color-text-muted
  #51607a`, `--color-border #d5dcea`; success/error/warning unchanged.
  Contrast (WCAG AA): accent on white 4.99:1 and on bg 4.65:1; text
  15.97:1; muted 6.36:1; white on accent 4.99:1, on brand blue 4.70:1,
  on navy 13.34:1; the status colours on their tints 4.74–5.71:1. The
  substitution: the brand blue is 4.70:1 on white but 4.42:1 on the page
  ground, so text uses the `#0066f4` tint and marks use the true blue;
  the teal (2.53:1) is never text. `theme-color` follows `--color-accent`
  through `siteMeta`.
- `index.html`: the icon links are `favicon.ico`, `favicon-32x32.png`,
  `favicon-16x16.png`, and `apple-touch-icon.png` at `?v=3`; no SVG
  favicon (no SVG source); JSON-LD `logo` is `/logo.png` instead of
  `og.png`. No Vite default, no monogram reference.
- `SiteHeader`: the text wordmark is `<img alt="superCPE">` from the
  hashed logo, height-capped at 2rem so the row does not grow, same link
  targets; a 3px brand-blue rule along the top. 025's tests still hold
  (no header in coming_soon, no course fact, no Registry string) and
  now assert the image and its alt on three surfaces.
- `ComingSoon`: redesigned — a white card with a brand-blue top rule on
  a soft blue/teal wash, the logo as the `<h1>` image, "COMING SOON" in
  navy, the unchanged form, single column at every width (the card
  stops at 28rem). No analytics, no third-party script, no font or
  image from another origin; the test walks every `src`/`href` and
  asserts none is absolute. `GET /api/v1/landing` gained no field.
- Certificate: the top mark is `backend/app/assets/brand/logo.png` by a
  `file:` URL (an uploaded logo is still a data: URI and still wins);
  the brand mark is a 6%-opacity seal behind the award; the frame is
  brand blue, the inner rule teal, the heading and credit line navy,
  the sponsor rule navy, the footer rule teal. `<meta
  name="dcterms.created">` carries the snapshot's `completed_at`, so
  the PDF's `/CreationDate` is the completion instant and two renders
  are byte-identical (the 032 renders already were, by accident of
  WeasyPrint writing no date; now it is by design and pinned). The
  fetcher is unchanged (data: and files under `app/assets/`). A render
  with the seal, the logo, three DejaVu faces, and a full snapshot is
  195 KB. `docs/certificate-sample-033.png` is what shipped.
- `AdminNav`: `useMediaQuery("(max-width: 720px)")` (a new
  `useSyncExternalStore` hook, `frontend/src/hooks/useMediaQuery.js`;
  answers false and never subscribes where `matchMedia` is missing)
  decides the layout. Narrow: the brand mark and "Admin", a Menu
  button (`aria-expanded`, `aria-controls`), Sign out; the button
  toggles a vertical list of the nine links and the email. Wide: one
  wrapping row (`flex-wrap: wrap` on the row and the link group), the
  email, Sign out. Sign out behaviour unchanged (`/login`). The screen-
  shot run caught that `hidden` lost to the panel's `display: flex`;
  `.menu[hidden] { display: none }` fixes it.
- `AdminSponsor`: the "Certificate" card now says "Certificates carry
  the superCPE logo; upload a different mark to replace it."; comments
  in `sponsor.py`, the model, the schema, and `api/sponsor.js` follow.
- Docs: OPERATIONS.md "Site identity (022)" replaced by "Brand assets
  (033)" (the source, the script, `--check`, the cache facts, the
  Flaticon retirement, the renderer's system deps under "Certificate
  look (032)", which is edited to name the brand logo). CLAUDE.md rule
  4 and the Commands block gain the lint line (pyflakes, oxlint,
  `sync_brand.py --check`). `docs/decisions/2026-09-13-brand-assets.md`.
  ROADMAP improvement note on the superseded 032 draft and the deferred
  `logo_path` slot. COMPLIANCE.md: four rows appended (below).
- Tests: backend 579 → 584 (`test_identity.py`: the PNG/ICO favicon
  set, no `favicon.svg` or monogram in `index.html`, pinned sizes for
  every icon and the OG card, the JSON-LD logo resolves to `logo.png`
  and the three logo copies are one file, maskable purpose in the
  manifest, no Registry-named asset or Registry words in the brand
  files; `test_certificates.py`: the brand logo and seal are the mark
  without an upload and embed at their pixel sizes, an upload replaces
  the logo and keeps the seal, byte-identical double render with the
  snapshot's date and under 500 KB, self-contained (every font
  embedded and DejaVuSans, no annotations, no URI, no http, no external
  file spec), no Registry words without the claim, and `sync_brand.py
  --check` run as a subprocess replaces the identity-script equality
  test). Frontend 137 → 144 (`AdminNav.test.jsx`: narrow hides the
  links until Menu, Menu opens them with the email, Sign out present in
  both states and called once, wide has no button, no matchMedia falls
  back to wide, the mark has empty alt; `ComingSoon.test.jsx`: the
  logo is the heading, nothing from another origin, no link at all,
  the form submits; `SiteHeader.test.jsx` and `AdminSponsor.test.jsx`
  follow the wording). All existing certificate text-extraction tests
  pass unchanged.

**Standards touched**
- 9.01 — printed page 21. The eleven items, read again against the
  template after the mark and colour changes: nothing added, dropped,
  or reworded; every item still extracts as one line. COMPLIANCE.md
  row added.
- 9.01.1 — printed pages 21–22. The awarding entity is still the
  "Authorized by" line from `sponsor_legal_name`. Same row.
- 8.01 — printed page 20. The landing page and the OG card were
  redesigned and disclose no item; the payload key set is unchanged.
  COMPLIANCE.md row added; the Registry-claim rule on the brand assets
  is its own row (9.01 item 8).
- 9.02 / 9.02.2 — printed page 22. Stored PDFs are never re-rendered;
  from 033 on they are self-contained and byte-comparable to their
  snapshot. COMPLIANCE.md note row added.

**Decisions**
- **One source, copy by script** (`docs/decisions/2026-09-13-brand-
  assets.md`). Reverses the 022 decision to generate identity assets
  from a placeholder and the 032 Decision "The monogram is drawn as
  code, not taken from the favicon": both were stopgaps for the absence
  of a brand, and the brand now exists. The Flaticon favicon is retired.
- **The sponsor mark is the brand mark.** The default certificate mark
  is the brand logo. `sponsor_profile.logo_path` (032) is not removed —
  the spec lists a per-sponsor slot as out of scope, and removing a
  shipped column and route would be a reversal it did not ask for —
  but it is an override, not a multi-sponsor feature; a real slot
  returns only with a second sponsor (001).
- **PNG favicons, no SVG.** The sources are raster; wrapping a PNG in an
  SVG would gain nothing. The 022 `favicon.svg` assertions were
  rewritten rather than kept, since the spec's "SVG preferred" was a
  preference and the alternative was drawing one.
- **Accent text is a tint, true blue is for marks** — the recorded
  values above.
- **Creation date from the snapshot**, so the stored-once record is
  checkable by comparison, and no `now()` reaches the bytes.
- **The seal is decoration** at 6% opacity behind the award, drawn
  before the text so extraction is unaffected; it costs 100 KB of the
  195 KB PDF. Drop it if size ever matters.
- **024 stands**: no paragraphs, no policies footer, no Registry block
  on the landing page. The spec's "conditional Registry block … existing
  behavior" was not existing behaviour, and its own hard rule says no
  Registry text; re-adding a landing read would reverse 024 without
  being asked to.
- **`useMediaQuery` decides the admin layout in JavaScript**, not CSS
  alone, so the narrow state is testable in jsdom and the menu button
  exists only where it is needed.

**Known gaps**
- Acceptance 8 (deploy, hard-refresh production, the favicon and
  `og.png`, a link previewer, a production certificate): not yet run by
  the operator.
- Acceptance 2's Safari "Add to Home Screen" and the OG card in a real
  previewer were not exercised; the tab icon links and `/og.png` were
  checked in headless Chrome against the dev server.
- Acceptance 5's "opens with network disabled" is asserted structurally
  (`test_certificate_is_self_contained`), not by opening the file in a
  viewer with the network off.
- Acceptance 3, 4, 6 were checked with headless Chrome driven over its
  debugging protocol against the local API and dev server (screenshots
  at 375, 720, and 1280; the admin menu closed, open, and Sign out from
  the open menu landing on `/login`). The nav itself is 311 px wide at
  375 and needs no horizontal scroll, but two admin page *bodies* are
  wider than a phone and make Chrome's mobile viewport zoom out: the
  create-course row on `/admin/courses` (514 px, the inputs and button
  do not wrap) and the accounts table on `/admin/accounts` (949 px).
  Pre-existing, outside the nav, report not build.
- The header at 375 with a participant signed in wraps to two rows
  (logo; then the three links, the email, and Sign out) with no
  overflow, so it was left as 025 built it.
- Dane's `apple-touch-icon.png` has a transparent ground, which iOS
  composites over black. Copied verbatim as supplied; an opaque version
  in `brand/` replaces it with one script run (noted in the README).
- Two local-only accounts (`shot-admin@local.test`,
  `shot-participant@local.test`) were created in the local dev database
  for the screenshot run and left there (accounts are never deleted;
  the dev database is test data).
- The working tree also carries the operator's uncommitted edits to
  `deploy/deploy.sh` and the OPERATIONS.md "Rollback" section (image
  pruning after a healthy deploy) from before this session; not part of
  033 and not touched.
- Open question 2 (a brand typeface): none was supplied, so the system
  stack and DejaVu stand, as the default said.
- The image built (`docker build -f deploy/Dockerfile .`) and a smoke
  render inside it produced a byte-stable PDF with both brand files
  present; size 1.55 GB, the same as 032 — no new package.
- pyflakes still reports the pre-existing unused imports 030 listed;
  oxlint's remaining warnings are all on untouched files.
