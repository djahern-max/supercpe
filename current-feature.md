# Feature 023c — Walkthrough corrections: certificate layout, review feedback, operator signals

Corrective feature from the 2026-09-10 production walkthrough of `ATO`
(SEC-01), Stages 4–9, run after 023b. Fixes only, no redesign. Anything
that turns out to need a design decision is reported, not built.

## Findings being fixed

**D1. Certificate renders most 9.01 items off the page.** Certificate
2026-000001 has the correct data but draws it past the right edge of a
612pt page. Text positions extracted from the PDF:

| x (pt) | Text | 9.01 item |
|---|---|---|
| 765 | superCPE, LLC | (1) sponsor name |
| 765 | Test User | (2) participant name |
| 1571 / 1776 | Account Takeover: … / Stop It | (3) course title |
| 706 | Location: Not applicable (self study) | (5) location |
| 1203 | Type of learning program: Self study | (6) program type |
| 1674 | CPE credit: 1.2 in Information Technology | (7) credit by field |
| 681 | National Registry of CPE Sponsors ID: … | (8) sponsor ID |
| 675 / 651 | Verify this certificate at … / code | (019 verification) |

Visible lines (completion date, 50-minute statement, developer and
reviewer line, certificate number) each follow an explicit line break.
Every other line starts at the previous line's right end. This is the
x position not returning to the left margin between cells (for fpdf2,
the `new_x` default after `cell`/`multi_cell`). The snapshot is correct.
Only the renderer is wrong. The same PDF is in the audit bundle, so the
9.02.2 file of record carries the defect.

Existing tests likely pass because text extraction ignores the page
boundary. The new test must check positions, not presence.

**D2. Review-question feedback disappears (5.01.2.2).** In the text
reader, answering a review question shows correct or incorrect with the
explanation for under a second. Then the question redraws as "You
answered this question earlier. Answer it again to see the feedback."
5.01.2.2 requires feedback that, at a minimum, indicates "correct" or
"incorrect," with the goal of reinforcing understanding. A sub-second
flash does not meet it. Likely cause: the answer POST triggers the
payload refetch that unlocks the next sections, and the refetch resets
the question's local state. Confirm the cause in Task 0.

**D3. Health reports `storage: error` with no log of why.** Production
health returns 503 with `"storage":"error"` while `bucket_versioning` is
ok and the text reader's own Spaces reads work. Nothing is logged, so
the operator cannot diagnose it.

**D4. `deploy.sh` misreports an unhealthy new version as the old one.**
On a deploy where health returned 503 while already reporting the new
sha, the script printed "Health never reported <sha> — the old version
may still be running." It treats any non-2xx as a version mismatch.

**F1. Video wording on the text assessment.** A failed attempt says
"Consider re-watching the lessons" on a study-guide course.

**F2. "N of M lessons watched"** counts a text lesson as watched from
the start (reported by 023b).

**F3. Section titles render twice.** The reader prints the manifest
section title, and each section's markdown opens with the same text as
an H1.

## In scope

1. Task 0 (establish), then D1–D4 and F1–F3 as below.
2. **D1:** the renderer returns to the left margin after every line, so
   every text run lies within the page. Do not re-render or overwrite
   stored certificates. Objects under `certificates/` are write-once
   (ROADMAP 012). 2026-000001 stays as issued. The fix applies to new
   completions.
3. **D2:** feedback stays visible after an answer until the participant
   acts again (answers another question, re-answers, or navigates). The
   unlock refetch must not clear it.
4. **D3:** the health storage check logs the exception class and message
   (never credentials or signed URLs) when it fails. Do not guess at
   the underlying cause. The operator reads the log line after deploy.
5. **D4:** `deploy.sh` distinguishes three outcomes: version not yet
   reported (keep waiting, then fail as "old version may still be
   running"); new version reported but unhealthy (report the component
   statuses from the body and exit non-zero with that message); new
   version healthy (success).
6. **F1:** the failed-attempt message is kind-aware. For text, say
   "re-reading the guide."
7. **F2:** a text lesson counts as read only when every section is
   unlocked and every review question after them is answered. The label
   says "read," not "watched," for text lessons.
8. **F3:** reader-side only. When a section's markdown opens with a
   heading whose text matches the manifest section title, render the
   title once. No contract change, so `docs/course-package.md` and
   video-tool stay untouched. Confirm the H1 is not double-counted, or
   newly excluded, in word count: the rendering change must not move
   the computed credit.

## Out of scope (report, do not build)

- **Who may record a 4.02 review.** 023b found that any admin or
  reviewer session can record a review naming any SME, with
  `recorded_by` stamping who typed it. The Standards do not say who
  enters the record. 4.02 requires the sponsor to ensure review by
  someone other than the developer, and 9.02.2(4) requires retaining
  reviewer names and credentials. Recording on a reviewer's behalf from
  a signed attestation is a legitimate sponsor practice. Restricting it
  is a design decision for `docs/decisions/`, not a fix. **In scope
  instead:** if the audit bundle omits `recorded_by`, add it (see Task
  0.4), so the file of record shows who entered each review.
- The 4.02.1 impractical-review path (ROADMAP question from 023b).
- Pinning the Caddy base images. The 2026-09-10 deploy spent 228s
  rebuilding `xcaddy` because `caddy:2-builder` moved upstream. Add a
  ROADMAP note only.
- Stripe, email, the uptime monitor, review-question density in SEC-01.

## Locators

Find these by grep and record the actual paths in the changelog: the
certificate renderer (PDF library calls); the certificate storage and
the audit-bundle certificate copy; the reader question component used
by `MyLesson.jsx` and `AdminCoursePreview.jsx`; the health endpoint's
storage check; `deploy/deploy.sh` wait loop; the assessment result page;
the My courses progress label and its backend source.

## Task 0 — establish

1. **D1:** which PDF library and which calls produce the drift? Are all
   certificate text lines produced by one function (one fix) or several?
2. **D2:** confirm the cause. Does the refetch remount or reset the
   question component?
3. **F2:** does "N of M lessons" feed any gate, completion record,
   certificate, or audit-bundle field, or is it display only? If it
   feeds anything, say so first. That raises it from friction to defect.
4. Does the audit bundle's review record include `recorded_by`?
5. Are certificate PDFs stored at issue (write-once under
   `certificates/`) and served from storage on download? The walkthrough
   suggests yes. Confirm.

## Data model

None expected. If a migration appears necessary, stop and report.

## Tests

- **D1:** render a certificate from a realistic snapshot (long course
  title that wraps, legal entity name, sponsor ID, verification code).
  Assert **every text run's x and y lie inside the MediaBox** and within
  the margins, using positioned extraction (e.g. pypdf `visitor_text`
  with the text matrix). Assert each 9.01 item that applies appears
  among the in-page runs. A test that only checks "text present"
  does not count.
- **D2:** after answering, the feedback element remains after the
  unlock refetch completes. Correct and incorrect paths are both covered.
- **D3:** a failing storage check logs one line with the exception
  class. No secret-shaped strings in the log.
- **D4:** unit-test the wait loop's three outcomes (stub the health
  response).
- **F1, F2, F3:** kind-aware message; text lesson not counted as read
  until its questions are answered; single title render; word count
  and credit for the SEC-01 fixture unchanged.
- Full suite green (baseline 438).

## COMPLIANCE.md rows

- 9.01: the certificate renderer is tested for in-page placement of
  every item, not only presence. Note that certificates issued before
  023c (test database only) carry the layout defect and were not
  rewritten (write-once).
- 5.01.2.2: review-question feedback persists until the participant's
  next action.
- 9.02.2(4): the audit bundle shows who recorded each review (if Task
  0.4 required the change).

## Acceptance

1. Local: a fresh participant completes SEC-01. The new certificate,
   **viewed as a rendered page** (not text-extracted), shows sponsor
   name, participant name, course title, completion date, location,
   program type, credit by field, sponsor ID, the 50-minute statement,
   and the verification line.
2. Local: answering a review question leaves the feedback on screen.
3. Typecheck and check pass. Suite green.
4. Production (operator): push, then deploy with the sha from
   `git rev-parse --short origin/main`. `deploy.sh` now reports "new
   version running, unhealthy: storage" rather than "old version." Read
   the storage log line and record the cause in the changelog. If it is
   a configuration fix, record it in OPERATIONS.md.
5. Production (operator): a second fake participant, enrolled by admin,
   completes `ATO` with exactly 5 of 7 correct (the boundary pass not
   yet tested). The certificate PDF shows every item in acceptance 1.
   Then change that participant's name and download again. The
   certificate must not change (Stage 8 check).
6. Production (operator): export the audit bundle. It contains the new
   certificate. The credit calculation shows 7,582 words, 12 questions,
   1.286, and 1.2. Review records show `recorded_by`.

## When done

Write the changelog entry only after acceptance 4–6 pass on production.
Include the Task 0 answers and the storage cause from acceptance 4.
Append only.

---

## Draft changelog entry — DO NOT append to CHANGELOG.md until acceptance 4–6 pass on production

Built 2026-09-10. Local acceptance 1–3 pass (see "Status" below). Fill
in the two `[[…]]` placeholders from the production run, then move this
entry to the end of `CHANGELOG.md` verbatim.

    ## 023c — Walkthrough corrections: certificate layout, review feedback, operator signals
    Shipped: [[YYYY-MM-DD of the production deploy]]

    **Task 0 answers**
    - D1: fpdf2 2.8.3. Every certificate line goes through one helper,
      `_Certificate.line_out` in `backend/app/services/certificates.py`,
      which called `multi_cell(..., align="C")` with fpdf2's default
      `new_x=XPos.RIGHT`: the cursor stayed at the cell's right edge, so
      every line not preceded by an explicit `ln()` (`spacer`) started
      where the previous one ended. One function, one fix. Reproduced
      locally before the change: the legal name at x=765, the participant
      name at 765, the title at 1567, the course code at 2257 on a 612pt
      page — the walkthrough's table exactly.
    - D2: confirmed. The refetch does not remount the question component
      (its key is the stable `question_key`); `Reader.jsx` held the
      verdicts in state and cleared them in `useEffect(() => setResults({}),
      [lesson])`. `MyLesson.jsx`'s `onAnswered` reloads the payload into a
      new object, so the effect fired after every answer and the question
      fell back to "You answered this question earlier".
    - F2: display only. `lessons_watched` was computed in
      `_summary_fields` (`backend/app/routers/my.py`) and `_enrollment_out`
      (`backend/app/routers/admin_enrollments.py`) from
      `furthest_seconds >= duration_seconds - 1`; a text package's
      duration is not watch time, so the test held from the start. Nothing
      that gates the assessment (`assessment_available`), records a
      completion, renders a certificate, or enters the audit bundle reads
      it. Friction, not defect.
    - Task 0.4: the audit bundle already writes `recorded_by` for every
      review (`_people_files` in `backend/app/services/audit_bundle.py`,
      column list at the reviews CSV). No change; the 9.02.2(4) COMPLIANCE
      row is not touched.
    - Task 0.5: confirmed. `ensure_rendered` in
      `backend/app/services/completions.py` renders once, stores at
      `certificates/{certificate_number}.pdf`, and sets `certificate_key`;
      a completion that already has a key is returned untouched. Every
      download (`backend/app/routers/my.py`, `admin_enrollments.py`,
      `services/delivery.py`) and the audit bundle stream that stored
      object. 2026-000001 stays as issued.

    **What changed**
    - D1 — `line_out` in `backend/app/services/certificates.py` passes
      `new_x=XPos.LMARGIN, new_y=YPos.NEXT`. `positioned_runs` and
      `test_every_text_run_lies_inside_the_page` in
      `backend/tests/test_certificates.py` extract every text run with
      its text-matrix position and measure its width with the renderer's
      own DejaVu metrics, then assert start x, end x, and y are inside the
      20 mm margins of the 612×792 MediaBox — and that each applicable
      9.01 item is among those in-page runs. Stored certificates are not
      rewritten.
    - D2 — `frontend/src/components/Reader/Reader.jsx` keeps the verdicts
      keyed by `lesson.lesson_id` and derives the visible results during
      render; the reset effect is gone (and with it the
      `set-state-in-effect` lint warning). A refetch of the same lesson
      keeps the feedback; a different lesson starts over.
      `Reader.test.jsx` covers correct, incorrect, and the different-lesson
      reset.
    - D3 — `_storage_check` in `backend/app/routers/health.py` logs one
      `app.health` ERROR line on failure: exception class and message,
      with anything after `?` cut so a signed URL's query string can never
      appear; a bucket that answers but has no sentinel logs that and
      names `write-sentinel`. Three tests in `backend/tests/test_health.py`,
      including one whose exception message carries `X-Amz-Signature` and
      asserts it is not logged.
    - D4 — the wait loop moved from `deploy/deploy.sh` to
      `deploy/wait-for-health.sh <sha> <url> [attempts] [sleep]`, which
      reads the HTTP status separately from the body and exits 0 (healthy
      new version), 1 ("New version <sha> running, unhealthy (HTTP 503):
      storage …", components read from the body), or 2 ("Health never
      reported <sha> — the old version may still be running"). It polls
      the whole window in every case and classifies by the last body.
      `deploy.sh` execs it. `backend/tests/test_deploy.py` runs the script
      against a fake `curl` for all three outcomes plus a dead endpoint.
      `docs/OPERATIONS.md` "Routine deploy" step 3 describes both failure
      lines and the log command for the storage cause.
    - F1 — `lessons_kind` ("text" | "video" | "mixed") on `AssessmentInfo`
      (both the preview route and the enrollment route);
      `frontend/src/components/Assessment/retryAdvice.js` picks
      "re-reading the guide" / "re-watching the lessons" / both.
      `Assessment.test.jsx` drives a failed attempt for a text and a video
      course.
    - F2 — `lesson_done` and `lessons_done` in
      `backend/app/services/enrollments.py` (video: furthest point within
      `WATCHED_TOLERANCE_SECONDS` of the end; text: every review question
      answered — the last body section opens only when the questions
      before it are answered, and the rest are the questions after it).
      `progress()` now carries `done` per lesson. `lessons_watched` is
      renamed `lessons_done` and joined by `lessons_kind` on
      `MyEnrollmentSummary` and `AdminEnrollmentOut` (`lessons_kind`
      from the new `courses.lessons_kind`); `MyLessonProgress` gains
      `done`. `frontend/src/pages/MyCourses/progressLabel.js` says
      "read" / "watched" / "read or watched"; `AdminCourseDetail.jsx`
      follows. Tests in `backend/tests/test_text_packages.py` walk 0 → 4
      → 5 answers and assert the count flips only at 5.
    - F3 — `stripLeadingTitle` in
      `frontend/src/components/Reader/sectionTitle.js`: when a section's
      markdown opens with a heading (any level, emphasis and spacing
      ignored) equal to the manifest section title, the reader drops that
      heading and prints the title once. Reader-side only; no contract
      change. `test_the_h1_matching_the_section_title_is_counted_exactly_once`
      pins that the count is taken from the shipped markdown alone (the
      fixture's 64 words include its heading's three, before and after).
    - The frontend gained a test runner: `vitest` + `jsdom` as
      devDependencies, `npm test`, `test` and `esbuild.jsx` blocks in
      `frontend/vite.config.js`. Five test files, 17 tests.
    - `ROADMAP.md`: two improvement notes (who may record a 4.02 review;
      pin the Caddy base images). `COMPLIANCE.md`: 9.01 and 5.01.2.2 update
      rows.

    **Standards touched**
    - 9.01 — the renderer is tested for in-page placement of every item,
      not presence; certificates issued before 023c (test database only)
      keep the defect, write-once.
    - 9.02.2 — the audit bundle's certificate copy is the stored PDF, so
      bundles exported before 023c carry the same defect; new completions
      are correct. `recorded_by` was already in the bundle.
    - 5.01.2.2 — review-question feedback persists until the participant's
      next action.
    - 6.01.2 sub-ii — the failed-attempt page still says nothing per
      question; only its one line of advice changed wording.
    - 7.02.6 — untouched; F3 is proven not to move the count.
    - 4.05.2 — the health endpoint the monitor watches now explains a
      storage failure in the log.

    **Decisions**
    - `lessons_watched` renamed rather than kept with a new meaning: a
      field that counts read lessons under a name that says "watched"
      would mislead the next reader. Both consumers are in this repo.
    - The deploy wait polls the full window even after seeing the new sha
      unhealthy, because a component can still be coming up; the
      classification uses the last body. The spec's outcome 2 says "exit
      non-zero with that message" and does not say when; sixty seconds of
      patience costs nothing the operator is not already waiting for.
    - The storage log line cuts everything after `?` rather than
      pattern-matching signature parameters: a query string is the only
      place a signed URL carries secrets, and cutting it is simpler to
      trust than a list of parameter names.
    - A text lesson with no review questions is "read" vacuously. The
      publish gate's 5.01.2.1 review minimum (`review_minimum` in
      `backend/app/services/readiness.py`) is per course, so a course
      with none cannot publish, but one lesson of a multi-lesson course
      could still carry none and would count as read from the start.
      Display only; noted, not built around.
    - A frontend test runner was added (two dev-only packages) because
      D2, F1, and F3 are frontend behaviours the spec requires tests for,
      and there was no way to test a React component without one.

    **Storage cause (acceptance 4)**
    [[Paste the `health storage check failed: …` log line from the
    production deploy and say what it was. If it was a configuration fix,
    record it in OPERATIONS.md too.]]

    **Known gaps**
    - Acceptance 2 (feedback stays on screen) was verified by the
      component test, not in a browser: this session has no browser.
    - The SEC-01 package is not in this repo (it is a video-tool export),
      so "word count and credit for the SEC-01 fixture unchanged" is
      pinned on the ASC842 fixture here and checked on production in
      acceptance 6 (7,582 words, 12 questions, 1.286, 1.2).
    - `MyCourse.jsx` (the enrollment detail page) still shows "Study
      guide" per text lesson and does not use the new per-lesson `done`;
      not in the spec's list of surfaces.
    - Frontend lint's pre-existing warnings (SessionContext, MyLesson,
      AdminCoursePreview, Player, PurchaseSuccess, VerifyCertificate) are
      untouched; the Reader's is gone.
