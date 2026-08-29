# 011 — Program evaluation, policies, retention, and the audit bundle

## Goal

Close out the Section 9 documentation set (ROADMAP structural difference
5): every element 9.02.2 lists for a self study program is now in rows,
and one admin action exports them for a course as a single zip a NASBA
reviewer could read cold. Along the way, build the two things that set
still lacks — participant evaluations (4.04) and the published policies
(8.01 items 8–11) — and make the five-year retention period a named
constant instead of a sentence in COMPLIANCE.md.

This is the last Phase A feature before deployment. When it ships, the
NASBA application packet described in ROADMAP Phase B is producible from
the admin UI.

## In scope

- `evaluations` (4.04.1's five elements), solicited after every passing
  assessment, skippable, one per completion.
- `evaluation_reviews`: a dated record that the sponsor reviewed a
  course's evaluation results (4.04.2), with the summary as of that date.
- Policies as append-only versions: registration/attendance, refund and
  cancellation, complaint resolution, plus the re-take policy derived from
  `RETAKES_ALLOWED`. Public `/policies` page and payload; the course page
  links to it; the coming-soon gate applies as it does to the catalog.
- `RETENTION_YEARS` constant; `retain_until` derived and shown on
  completions and in the bundle.
- 4.05.3 items 1 and 4: an overview of topics on the course page and a
  "How this course works" instructions page.
- The per-course audit bundle export, logged.
- Certificate font fix: bundle a Unicode TTF so participant names render
  correctly (010's Latin-1 gap).

## Out of scope

- Emailing evaluation results to developers (4.04.2 "should inform") —
  no email exists until 018; the admin summary page names the developer.
- 4.05.3 items 2 and 3 (keyword search, glossary): these are content and
  need the course-package contract to carry a glossary. Record them as a
  ROADMAP improvement note naming both repos; do not build them here.
- Deployment (012). Spaces storage, production config.
- Evaluation of instructors (4.04.1 item 5): self study has none;
  recorded as not applicable, never asked.
- Any change to `docs/course-package.md`.

## Locators — read these paragraphs before writing code

- **4.04, 4.04.1** — an effective means of evaluating quality; evaluations
  "must be solicited from participants … for the overall program" and
  determine whether (1) objectives were met, (2) prerequisites were
  appropriate, (3) materials including the qualified assessment were
  relevant, (4) time allotted was appropriate, (5) instructors were
  effective where applicable.
- **4.04.2** — sponsors "must periodically review evaluation results" and
  should inform developers.
- **4.05.3** — the six minimum items of self study instructional
  materials. Items 5 and 6 are 006/007; items 1 and 4 are here; 2 and 3
  are the improvement note.
- **8.01 items 8–11, 8.01.1** — registration and attendance requirements,
  refund/cancellation policy, complaint resolution policy, and the
  official NASBA sponsor statement "if an approved NASBA sponsor"; policies
  must be "formalized, published, and made available."
- **9.02** — five-year retention.
- **9.02.2 (1)–(7)** — the seven self study documentation elements. The
  bundle's README maps each to its files, in this order.

## Data model

One migration. CHECKs by hand. Nothing here is ever deleted.

**`evaluations`**
- `id`, `completion_id` FK RESTRICT unique, `submitted_at`,
  `objectives_met`, `prerequisites_appropriate`, `materials_relevant`,
  `time_appropriate` — each smallint CHECK 1–5 — `instructors_effective`
  always null with a CHECK that it is null (self study; the column exists
  so the record visibly answers item 5 as not applicable), `comments`
  text (may be blank), `objectives_snapshot` JSONB (the objectives the
  participant was rating, copied from the completion's pinned packages).
- Constants in `app/constants/evaluation.py`: `SCALE_MIN = 1`,
  `SCALE_MAX = 5`, the five prompts as text (so the wording that was asked
  is code-versioned and quoted in the bundle), `SOLICIT_UNTIL_DAYS = 30`
  (how long after completion the prompt keeps appearing; ours, not
  NASBA's — say so).

**`evaluation_reviews`**
- `id`, `course_id` FK RESTRICT, `reviewed_at`, `reviewed_by_account_id`
  FK RESTRICT, `summary_snapshot` JSONB (counts and means per element,
  n, comments excerpt list, as of `reviewed_at`), `note` text,
  `informed_developer` boolean (the admin's attestation that the
  developer of record was told; the bundle prints it as stated).
  Append-only.

**`policy_versions`**
- `id`, `kind` CHECK IN ('registration', 'refund', 'complaint'),
  `body` text (Markdown), `effective_at`, `created_at`,
  `created_by_account_id` FK RESTRICT. Append-only; the current version of
  a kind is the latest `effective_at <= now()`. A kind with no version is
  a launch-readiness missing item (task 4).
- The re-take policy is not a version: it is rendered from
  `RETAKES_ALLOWED` and `PASSING_PCT` so it cannot disagree with the code.
- The NASBA sponsor statement (item 11) is a constant
  `NASBA_SPONSOR_STATEMENT` in `app/constants/certificate.py`, rendered
  only when `may_claim_registry`; the text is the Registry's standard
  wording and the constant's docstring says it may only appear when true.

**`audit_exports`**
- `id`, `course_id` FK RESTRICT, `generated_at`,
  `generated_by_account_id` FK RESTRICT, `sha256`, `size_bytes`,
  `storage_key`. Append-only; every export is kept (it is itself
  documentation of what the sponsor could produce on a date).

**Constants:** `RETENTION_YEARS = 5` in `app/constants/retention.py`
with 9.02 quoted; `retain_until(completed_at)` in
`app/services/retention.py`. Nothing enforces deletion after it — the
constant exists so the bundle and admin can state the date.

## Tasks

1. **Models and migration** as above.

2. **Evaluations.** `app/services/evaluations.py`: `solicit(completion)`
   → whether to show the prompt (no evaluation yet, within
   `SOLICIT_UNTIL_DAYS`); `submit(completion, ratings, comments)` —
   refuses a second; `summary(course)` — n, mean and distribution per
   element, comments in `submitted_at` order; `record_review(course,
   account, note, informed_developer)` writes the snapshot.
   Routes: `POST /api/v1/my/completions/{id}/evaluation`,
   `GET /api/v1/admin/courses/{code}/evaluations` (summary + rows),
   `POST /api/v1/admin/courses/{code}/evaluation-reviews`,
   `GET …/evaluation-reviews`. A `evaluation_review_due` warn finding in
   `readiness.check` when a course has evaluations newer than its latest
   `evaluation_reviews` row by more than `EVALUATION_REVIEW_DAYS` (90;
   ours) — "periodically" made concrete and reported, not enforced.

3. **Policies.** `app/services/policies.py`: `current()` → the three
   kinds' current bodies plus the derived re-take text and, when
   `may_claim_registry`, the sponsor statement; `publish(kind, body,
   effective_at, account)`. Routes: public `GET /api/v1/policies` (behind
   `require_site_open_or_session` like the catalog), admin
   `GET/POST /api/v1/admin/policies` (history per kind, new version).
   The 004 public course payload gains `policies_url`; the course page
   links "Registration, refund, and complaint policies" above the
   enrollment call to action.

4. **Launch readiness.** The `/admin/sponsor` panel gains: each policy
   kind with no current version as a missing item ("Refund policy not
   published"), and `evaluation_review_due` per course. These are
   *launch* findings, not publish findings — a course may publish without
   them, but the site should not open. Add `site_open_blockers()` in
   `app/services/site.py` returning them; `set_site_mode(open)` refuses
   with the list (422). This is new: 009 let the flip through unchecked.

5. **Retention.** Constant and helper; `retain_until` on the admin
   completions table and every bundle record that has a `completed_at`.

6. **4.05.3 items 1 and 4.**
   - Overview of topics: the public course payload gains `outline` —
     lesson titles in order, each with its objectives (already derived
     by 004's `course_objectives`); the course page renders it as
     "What this course covers" above the objectives list. No new storage.
   - Instructions: a static participant page `/how-it-works` (and a
     `GET /api/v1/how-it-works` returning its Markdown so the bundle can
     include it) describing navigation, the review questions, the
     assessment (passing score, re-takes, expiry — all read from
     constants so it cannot drift), and how the certificate is delivered.
     Linked from `/my/courses` and the course page.

7. **Certificate font.** Vendor `DejaVuSans.ttf` (and Bold) under
   `backend/app/assets/fonts/` with its license file; `render` registers
   it with fpdf2 and stops sanitizing. Test: a snapshot with a
   participant name containing "ễ" and "ł" renders and extracts
   unchanged. Re-render an existing 010 completion in acceptance to show
   the text is identical for Latin-1 names.

8. **The audit bundle.** `app/services/audit_bundle.py`:
   `build(db, course, generated_by) -> (bytes, manifest)`. Layout inside
   the zip, one top-level directory `<course_code>-audit-<YYYYMMDD>/`:

   ```
   README.md                     what this is; the 9.02.2 map below; who
                                 generated it and when; retention statement
   bundle.json                   generated_at, by, course code, every file
                                 with sha256 and byte size
   1-completion/
     completions.csv             per participant: name, email, enrolled_at,
                                 expires_at, completed_at, credit_awarded,
                                 certificate_number, retain_until
     attempts.csv                every attempt on the course: participant,
                                 started, submitted, status, score, passing_pct,
                                 package_versions
     attempt_answers.csv         attempt, question_key, chosen, correct
     review_answers.csv          enrollment, lesson, question_key, chosen,
                                 correct, answered_at   (5.01.2 engagement)
     certificates/<number>.json  every certificate_snapshot
     certificates/<number>.pdf   every rendered certificate
   2-credit/
     calculation.txt             005's as_text
     credit_breakdown.json       the stored per-lesson inputs
   3-expiration/
     enrollments.csv             enrollment, participant, enrolled_at,
                                 expires_at, status, package_versions
     policy.txt                  ENROLLMENT_DAYS and the 9.02.2(3) sentence
   4-people/
     developer.json              name, credentials, jurisdiction, license
                                 number, status, developer_used_technology
     reviewers.json              every reviewer ever named, same fields
     reviews.csv                 every course_reviews row incl. recorded_by,
                                 content_updated_at_reviewed, impractical_basis
     review_cycle.txt            cycle, last review, review_due_at
   5-evaluations/
     evaluations.csv             all rows, prompts quoted in the header comment
     summary.json                current summary
     evaluation_reviews.csv      the 4.04.2 log
   6-descriptive/
     course.json                 the public 8.01 payload as served today
     course.md                   the same rendered readable
     policies/<kind>-<n>.md      every policy version with effective_at
     how-it-works.md
   7-materials/
     <lesson_id>/v<n>/manifest.json, questions.json, transcript.md
                                 for every package version ever attached or
                                 pinned by an enrollment
     <lesson_id>/v<n>/video.txt  storage key, content_hash, duration, and
                                 "video omitted; retrieve by key" — videos
                                 are not zipped by default
   ```
   `include_video=true` on the request zips the mp4s too (large; the UI
   says so). CSVs are UTF-8 with a header row; timestamps ISO 8601 UTC.
   Every file is listed in `bundle.json` with its sha256; the zip's own
   sha256 goes on the `audit_exports` row and the zip is stored at
   `audits/<course_code>/<generated_at>.zip`.
   Route: `POST /api/v1/admin/courses/{code}/audit-bundle` (returns the
   export row), `GET …/audit-bundle/{id}.zip`, `GET …/audit-bundle`
   (history). Admin course page gains an Audit bundle card: Generate
   (with the include-video checkbox), and the history with size, sha256,
   and Download.

9. **README.md content.** Written by the service from a template: the
   sponsor name and legal name; "Documentation retained under Section 9
   of the 2026 Statement on Standards for CPE Programs for self study
   programs"; the 9.02.2 element → directory map with the element text
   quoted; a line that videos are retained in object storage under the
   listed keys; the registry status as of generation stated plainly
   ("This sponsor is not on the National Registry" when not — the one
   place that sentence is allowed, because it is the truth stated to an
   auditor, never a claim); generated by / at; retention statement with
   `RETENTION_YEARS`.

## Tests (`tests/test_evaluations.py`, `tests/test_policies.py`, `tests/test_audit_bundle.py`)

- Evaluation: prompt shown after completion, hidden after submit or after
  `SOLICIT_UNTIL_DAYS`; ratings outside 1–5 refused; `instructors_effective`
  cannot be set; second submission refused; summary means computed with
  `Decimal`; `evaluation_review_due` fires after `EVALUATION_REVIEW_DAYS`
  and clears when a review is recorded.
- Policies: no versions → three launch missing items; publishing a
  version clears its item; a future `effective_at` is not current until
  then; history retains every version; public route is gated by site mode
  exactly as `/courses`; the re-take text contains `RETAKES_ALLOWED` and
  `PASSING_PCT` as numbers; the sponsor statement is absent while
  `not_registered` (walk the payload) and present when registered.
- Site open refusal: `set_site_mode(open)` is 422 naming the missing
  policies; passes once published.
- Retention: `retain_until` is exactly `RETENTION_YEARS` after
  `completed_at`.
- Font: the two non-Latin-1 names round-trip through render and extract.
- Bundle: for a course with two enrollments, one completion, one failed
  attempt, one evaluation, two reviews, and a package updated once
  (so two versions are pinned somewhere): every file in the layout
  exists; `bundle.json` lists every file and each sha256 matches;
  `7-materials` contains both package versions; `completions.csv` has one
  row with the right credit and certificate number; `people/reviewers.json`
  carries license numbers (this is the one place they may appear);
  `README.md` contains "not on the National Registry" while
  `not_registered` and no other file under 6-descriptive contains
  "National Registry"; the `audit_exports` row's sha256 equals the
  sha256 of the returned bytes; a second generation adds a row and does
  not alter the first's stored zip.
- All prior tests pass; the count goes up.

## COMPLIANCE.md rows

| 4.04, 4.04.1 | evaluations solicited from participants for the overall program, covering the five elements | 011 | `evaluations` with the five columns (item 5 constrained null: self study); prompts in `app/constants/evaluation.py`; solicited on the result page and `/my/courses` for `SOLICIT_UNTIL_DAYS` | Solicited, not required: a participant may decline, and nothing withholds the certificate. Instructor evaluation is not applicable and the record says so. |
| 4.04.2 | sponsors must periodically review evaluation results and should inform developers | 011 | `evaluation_reviews` (dated, by account, summary snapshot, `informed_developer` attestation); `evaluation_review_due` warn finding after `EVALUATION_REVIEW_DAYS` | "Periodically" is 90 days by our choice; reported, not enforced. Informing the developer is an attestation, not an email (018). |
| 4.05.3 | minimum contents of self study instructional materials, items 1 and 4 | 011 | `outline` in the public course payload; `/how-it-works` page from constants | Items 2 (search) and 3 (glossary) are not built; ROADMAP improvement note names the contract change. Items 5 and 6 are 006 and 007. |
| 8.01 items 8–11, 8.01.1 | registration/attendance, refund/cancellation, complaint resolution policies published in advance; sponsor statement if an approved sponsor | 011 | `policy_versions` (append-only, effective-dated); public `/policies`; course page link; `NASBA_SPONSOR_STATEMENT` rendered only under `may_claim_registry`; `site_open_blockers` refuses opening the site without all three | Item 11 cannot be true until registration; the constant exists and is gated. |
| 9.02 | (existing row; replace the Gap) | 011 | `RETENTION_YEARS` in `app/constants/retention.py`; `retain_until` shown on completions and in every bundle record | Nothing deletes at the boundary; retention is a floor and the system keeps everything. |
| 9.02.2 (1)–(7) | the seven self study documentation elements | 011 | `app/services/audit_bundle.py`; `audit_exports` log; layout mapped element by element in the bundle's README | Method 1 records (2)(i) are absent by design (005). Videos are included by reference unless requested. |
| 9.02.2(5) | results of program evaluations | 011 | `5-evaluations/` in the bundle | — |
| 9.02.2(6) | program descriptive materials | 011 | `6-descriptive/` — the 8.01 payload, every policy version, the instructions page | — |

Append to the 9.01 row: the Unicode font.

## Acceptance

1. Migration runs on the 010 database.
2. As the participant who completed ASC842-PCX in 010: the result page
   and `/my/courses` show the evaluation prompt; submit it; it does not
   reappear. `/how-it-works` reads correctly and the numbers match the
   constants.
3. As admin: `/admin/sponsor` lists the three missing policies; flipping
   the site to open is refused naming them; publish all three; the
   refusal clears; `/policies` renders them with the re-take text; the
   course page links to it; "National Registry" appears nowhere on it.
4. Record an evaluation review on the course; the warn finding clears.
5. Generate the audit bundle without video; open the zip; every
   directory in the layout is present; `README.md` maps the seven
   elements and states the sponsor is not on the Registry; the
   certificate PDF from 010 is in `1-completion/certificates/`;
   `bundle.json` sha256s verify with `sha256sum`. Generate again with
   video; the mp4 is present and the history shows two rows.
6. Re-render the 010 certificate; the text is unchanged and the font is
   the vendored one (check the PDF's font list).
7. `pytest`: all pass; count exceeds 168.

## When done

- Changelog per CLAUDE.md, including: the choice of 90 and 30 days as
  ours, the decision that policies are versions rather than a single
  editable text, the decision to include videos by reference, and the
  new site-open refusal.
- COMPLIANCE.md rows above.
- ROADMAP improvement note: "4.05.3 items 2–3: the course package should
  carry a glossary (`manifest.glossary[]`, term/definition/source) and
  superCPE should render it with a term search — a contract change
  coordinated through `docs/course-package.md` and a video-tool feature
  to author it from the sources folder." Also note whether the
  effective-date paragraph at the end of the Standards (new self study
  programs first published: March 1, 2027) should be recorded anywhere
  in code — say what you concluded.
- For 012: list every storage key prefix now in use (`packages/`,
  `certificates/`, `audits/`) so the Spaces implementation and its
  backup policy cover all three, and note which are write-once.
