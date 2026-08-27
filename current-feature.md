# Current Feature

## Feature 007, The qualified assessment

## Goal
A participant can take the course's qualified assessment, be graded
server-side against the 70 percent cumulative floor, and get exactly the
feedback 6.01.2 permits: on a pass, the per-question record; on a fail, the
score and nothing else. The course knows whether its assessment questions
are enough, distinct from its review questions, forced-choice-free, and
covering three quarters of its objectives. Attempts are recorded now, in
preview form, so 010 can key them to an enrollment without changing the
engine.

## In scope
- Assessment minimums, objective coverage, duplicate and forced-choice
  checks as readiness findings
- `attempts` and `attempt_answers` tables, with a preview flag
- Start / submit / result endpoints, whole-assessment submission
- The feedback rule of 6.01.2 sub-ii, no test bank
- Retakes
- The assessment UI, and an admin attempts view

## Out of scope
- A test bank, and therefore the other branch of sub-ii. superCPE serves
  every assessment question every time.
- Nano learning's 100 percent rule and adaptive learning's path minimum.
- Recall-as-learning-strategy exemption from the duplicate rule.
- Completion, credit award, certificate. 010. This feature produces a
  passed attempt; it does not decide anything follows from it.
- Publish. 008 reads the findings.

## Locators
Read 6.01, 6.01.1, 6.01.2 in full, including sub-i and sub-ii and the
chart, and 9.02.2(1) for what an attempt record must be able to prove.
Then read 5.01.2.2 again so the contrast is fresh.

The rules, all from 6.01.2:
- Cumulative minimum passing grade of at least 70 percent before credit.
- Five questions per credit; below a full credit, the chart
  (0.2→2, 0.4→3, 0.5→4, 0.6→4, 0.8→5); above, per credit plus the chart
  for the remainder. The paragraph's own worked examples (5 credits → 25,
  5½ → 29) must be reproduced by the function.
- Duplicate review and assessment questions are not allowed.
- Forced choice (true/false, yes/no) is not permissible; three choices is
  the floor.
- The assessment must measure 75 percent or more of the learning objectives.
- Sub-ii, no test bank: on a failed assessment, the sponsor may not provide
  feedback; on a passed one, it may. Since a pass or fail is only known
  after the whole assessment is scored, **no per-question verdict may be
  shown while an attempt is open, and none may ever be shown for a failed
  attempt.** The assessment is a form submitted once, not a sequence of
  graded questions.

## Data model
Table `attempts`:
- id, course_id (FK), enrollment_id (nullable FK placeholder — add the
  column as nullable integer with no FK yet; 010 adds the constraint),
  is_preview (bool, not null), status (CHECK in open/passed/failed),
  started_at, submitted_at (nullable), score_pct (numeric(5,2), nullable),
  passing_pct (numeric(5,2), not null — snapshot of the threshold used),
  question_count (int, not null), correct_count (int, nullable),
  package_versions (JSONB: `[{package_id, version}]` at start, so the
  attempt can prove which questions were asked even after a re-export)
- Only one open attempt per (course, preview identity) at a time.

Table `attempt_answers`:
- id, attempt_id (FK cascade), question_id (FK), choice_id (FK),
  is_correct (bool, set at grading), answered_at
- unique (attempt_id, question_id)

`is_correct` is written at submit, never returned to the client for a
failed attempt. Write the test first.

## Constants
Add to `question_minimums.py`: `ASSESSMENT_PER_CREDIT = 5`, the chart,
`MIN_CHOICES_ASSESSMENT = 3`, `required_assessment_questions(credit)`.
New `app/constants/assessment.py`: `PASSING_PCT = Decimal("70")`,
`OBJECTIVE_COVERAGE_PCT = Decimal("75")`, `RETAKES_ALLOWED = True` with a
comment that retake policy is a sponsor choice the Standards do not fix,
that every attempt is retained regardless, and that 011 must disclose the
policy on the course page.

## Readiness findings (extend `readiness.check`)
- `assessment_minimum` (block) — counting assessment questions (≥3
  choices) below the required number; both numbers shown
- `assessment_forced_choice` (block) — any assessment question with fewer
  than 3 choices. Ingest already refuses this, so it can only arise from a
  fixture; keep the finding anyway
- `assessment_duplicate` (block) — an assessment question whose normalized
  stem (lowercase, whitespace collapsed, trailing punctuation stripped)
  equals a review question's stem in the same course. Message names both
  question keys and lessons
- `objective_coverage` (block) — the assessment's `objective_keys`, keyed
  by (package_id, key), cover fewer than 75 percent of the course's
  objectives (from `course_objectives`). Message shows covered/total and
  lists uncovered objectives by lesson

## Engine, `app/services/assessment.py`
- `start(db, course, identity) -> Attempt`: refuses if course credit is
  stale or any block finding exists (the assessment is not well-formed
  yet); records `package_versions`; question order is package position
  then question position; choice order as stored. No shuffling in this
  feature — say why in a comment: auditability of "what was asked" beats
  the marginal integrity gain, and a shuffle can be added later with the
  order stored per attempt.
- `submit(db, attempt, answers: {question_id: choice_id}) -> Attempt`:
  requires every question answered; grades; sets status by
  `score_pct >= passing_pct`; writes `attempt_answers.is_correct`.
- `result(attempt) -> dict`: for **passed**: score, status, and per
  question the chosen choice, the correct choice, the verdict, and the
  question's feedback. For **failed**: score, status, question count,
  correct count, and the retake affordance. Nothing per question. Not the
  correct count per objective, not which ones were wrong. The Standard
  says "may not provide feedback" and a count of correct answers is the
  outer limit of what a score already reveals.
- `abandon(db, attempt)` for an open attempt the participant walks away
  from; status becomes failed with `score_pct` null. Retained.

Identity for preview attempts: an opaque `preview_id` the admin frontend
generates once per session and sends as a header; stored on the attempt in
place of an enrollment. 010 replaces this with the enrollment id and the
preview path stays for admins.

## Endpoints (admin token now; 010 re-gates)
- `GET /api/v1/courses/{code}/assessment` — questions and choices, no
  answers, no feedback; plus `question_count`, `passing_pct`, and whether
  an open attempt exists
- `POST /api/v1/courses/{code}/assessment/attempts` — start
- `PUT /api/v1/courses/{code}/assessment/attempts/{id}/answers` — save
  partial answers (so a refresh does not lose work); no grading
- `POST /api/v1/courses/{code}/assessment/attempts/{id}/submit` — grade,
  return `result`
- `GET /api/v1/courses/{code}/assessment/attempts/{id}` — `result`, or the
  saved answers if still open
- Admin: `GET /api/v1/admin/courses/{code}/attempts` — every attempt with
  status, score, timestamps, preview flag, and per-answer detail (the admin
  may see everything; the participant may not)

## UI
`src/components/Assessment/`, mounted at
`/admin/courses/:code/preview/assessment` and later by 010.

- Opens with a plain statement: number of questions, the 70 percent
  requirement, that results come after all questions are submitted, and
  that retakes are allowed. One "Begin" button.
- All questions on one scrolling page, numbered, each with its choices as
  tappable rows. No verdicts, no colors, no hints of correctness anywhere
  while open. A sticky footer shows "N of M answered" and Submit, disabled
  until all are answered. Answers save on change.
- Submit asks once ("Submit all M answers?") and grades.
- Passed: score large, then each question with the chosen answer, the
  correct one marked, and the feedback text. A note that the course's
  completion is recorded (010 will make that true; for now the preview
  banner covers it).
- Failed: score large, "70 percent is required," correct count out of
  total, a "Try again" button, and a line suggesting re-watching the
  lessons. Nothing else. Resist adding anything here; the Standard is
  restrictive on purpose.
- Keyboard-navigable throughout.

Admin: `/admin/courses/:code` gains an Attempts card (count, pass rate,
latest) linking to `/admin/courses/:code/attempts` (table, click for
detail with every answer).

## Tests
- `required_assessment_questions`: the chart, 5.0→25, 5.5→29, 1.2→7
- duplicate detection: identical stems differing in case and trailing
  punctuation are duplicates; a stem differing by one word is not
- objective coverage: 3 of 4 objectives → 75 percent → no finding;
  2 of 4 → finding listing the two uncovered
- start refuses on stale credit and on a block finding
- submit refuses with unanswered questions
- 70.00 passes, 69.99 fails (construct question counts that produce these)
- the result payload for a failed attempt contains no `is_correct`, no
  `correct_choice`, no `feedback`, and no per-question array (walk it)
- the result payload for a passed attempt contains all of them
- the open-attempt questions payload contains no answers or feedback
- a second start while one is open is refused; abandon then start works
- `package_versions` on an attempt survives a re-ingest of the lesson
- admin attempts endpoint returns per-answer detail for a failed attempt
  (the admin sees what the participant may not)

## COMPLIANCE.md
Rows for 6.01, 6.01.1, 6.01.2 (one row each for: passing grade; minimums
and chart; duplicates; forced choice; objective coverage; sub-ii
feedback), and 9.02.2(1) with the Gap that attempts are not yet tied to a
participant. The sub-ii row's Where-in-code column should point at
`result()` and the failed-attempt payload test by name; that test is the
proof.

## Acceptance
- `pytest` passes; migration round-trips
- ASC842-PCX with the real lesson: readiness shows the assessment count vs
  required, and `objective_coverage` reports honestly (one lesson's 3
  assessment questions against 4 objectives — if that is under 75 percent,
  the finding is correct and the fix is in video-tool 04, not here)
- Preview: take the assessment, answer one wrong of three, submit → 66.67,
  failed, and the page shows nothing about which one; try again, all
  correct → passed, with feedback
- Network tab during a failed attempt: no correctness data anywhere

## When done
Append the 007 entry. Decisions: form-not-sequence because of sub-ii; no
shuffling; retakes allowed as sponsor policy. Known gaps: no test bank
branch; recall exemption not modeled; attempts not yet tied to
enrollment; retake policy not yet disclosed on the course page (011).
Then stop.
