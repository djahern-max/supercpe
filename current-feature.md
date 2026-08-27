# Current Feature

## Feature 006, Questions, and the player with review questions inside it

## Goal
Questions come out of the stored packages into real tables, superCPE knows
whether a course has enough of them for its credit, and a participant can
watch a lesson with review questions that pause the video at measured
points, answer, get feedback, and continue. This is the first real
participant experience and the biggest departure from abacadaba: review
questions live inside the video, not on a quiz page after it.

No accounts exist yet, so the player runs in an admin preview at
`/admin/courses/:code/preview`. It is built as the participant player,
behind the token for now; 010 mounts the same component for enrolled
participants and adds persistence.

## In scope
- Contract enforcement for `video.blocks` (video-tool 03)
- `questions` and `choices` tables normalized from packages, per version
- Review-question minimums against the course's credit (5.01.2.1)
- Server-side grading of review answers with feedback (5.01.2.2)
- The player component with in-video review pauses
- Admin question view with a readiness checklist

## Out of scope
- The qualified assessment. Feature 007 builds it and it has different
  feedback rules; nothing here may be reused for it without reading 6.01.2.
- Persisting review answers or watch progress. 010, keyed to enrollment.
- Publish. 008 reads the readiness checklist.
- Captions or transcript display (roadmap improvement note).

## Locators
Read 5.01, 5.01.2, 5.01.2.1, 5.01.2.2 before writing code, and read 6.01.2
sub-ii once so you know why the assessment must be built separately. Take
COMPLIANCE.md's Requirement column from the PDF.

Facts that shape this feature, all from those paragraphs:
- Review questions must be placed throughout the program at sufficient
  intervals for the participant to judge what to re-study. `after_block`
  plus measured block timings is how superCPE satisfies "throughout".
- Three per credit, with the one-fifth chart below a full credit
  (0.2→0, 0.4→1, 0.5→2, 0.6→2, 0.8→3, 1.0→3), and the chart again above
  each whole credit. Transcribe the chart from the PDF into a constant; the
  above-one-credit decomposition (`whole × 3 + chart[remainder]`) is an
  interpretation and the constant's docstring must say so.
- True/false questions do not count toward the minimum. Count a review
  question only if it has more than two choices.
- No minimum passing rate on review questions. Nothing here scores anyone.
- Feedback is mandatory and must at least say correct or incorrect. The
  package requires non-blank feedback text, so superCPE always has more than
  the minimum.

## Contract enforcement
`docs/course-package.md` now carries `video.blocks` (copied from video-tool
03; verify the two files are identical). Add the rules to
`packages.py` and the factory, with the rule numbers video-tool used.
`after_block` must be within `[1, len(blocks)]`, replacing the old
`narration_blocks` bound. Existing stored packages without `blocks` predate
the rule and are fixtures; the factory package must gain them.

## Data model
Table `questions`:
- id, package_id (FK cascade, indexed), question_key (the package's `id`,
  e.g. "q-01"), kind (CHECK in review/assessment), after_block (int,
  nullable; not null iff review), position (int, order within package),
  stem (text), feedback (text), objective_keys (JSONB list of objective ids
  from the manifest)
- unique (package_id, question_key)

Table `choices`:
- id, question_id (FK cascade), choice_key ("a"), text, is_correct (bool),
  position
- unique (question_id, choice_key); exactly one `is_correct` per question,
  enforced in the normalizer and by a test

Normalize at ingest: `packages.ingest` writes these rows after the package
row, in the same transaction. Also write a one-time backfill in the
migration for existing packages, or a script; either is fine, say which.

Questions belong to a package version, not to a course. A course's review
questions are those of its attached packages' current versions.

## Minimums
`app/constants/question_minimums.py`: `REVIEW_PER_CREDIT`,
`REVIEW_MINIMUMS` chart, `required_review_questions(credit: Decimal)`. Leave
room for 007 to add the assessment constants in the same file.

`app/services/readiness.py`: `check(db, course) -> list[Finding]` where a
Finding is `{code, level: "block"|"warn", message}`. This feature adds:
- `credit_missing` (block) — no fresh credit
- `review_minimum` (block) — fewer counting review questions than required;
  message shows both numbers and the credit they derive from
- `review_placement` (warn) — any lesson with zero review questions, or two
  consecutive blocks... keep this simple: warn if any lesson has no review
  question at all, since "throughout" cannot be met by a lesson with none
- `review_two_choice` (warn) — review questions with exactly two choices,
  which exist but do not count

008 turns "block" findings into a publish refusal. Nothing here refuses
anything; it reports.

## Grading
`POST /api/v1/courses/{code}/lessons/{package_id}/review/{question_key}`
with `{choice_key}` → `{correct: bool, feedback: str, correct_choice_key}`.
Grade on the server. **The question payload served to the player never
contains `is_correct`**; write a test that walks the whole public and
preview payload and asserts the field is absent. abacadaba shipped the
answer key to the browser once and had to build a replay test to prove it
was gone; do not make that mistake here.

The endpoint is stateless in this feature. Re-answering is allowed. Behind
the admin token for now; 010 moves it behind enrollment.

`GET /api/v1/courses/{code}/lessons/{package_id}/play` → everything the
player needs for one lesson: a presigned or local video URL from `Storage`
(add `url(key)` to the protocol; `LocalStorage` serves through a small
`/media/` route), the `blocks` list, and the review questions with their
`after_block`, stems, and choices (no answers).

## The player
`src/components/Player/` — one component, mounted by the preview page now
and by 010 later. Design brief, since this is the surface a participant
will spend most of their time on:

- The video is the page. One column, video at a comfortable reading width
  (not full-bleed), lesson title above, nothing else competing.
- A slim progress bar under the video with a tick at each review point.
  Ticks are visible before they are reached so the participant knows a
  question is coming.
- At a review point the video pauses and the question appears *in place*,
  as a panel over the video area with the same width, not a modal and not a
  sidebar. Stem, choices as large tappable rows, a Submit button. After
  submit: the verdict ("Correct" / "Not quite"), the feedback text, and a
  "Continue" button. If wrong, also a "Re-watch this section" link that
  seeks to the block's `start_seconds` and resumes.
- The participant must answer before continuing; any answer is fine (no
  passing rate). Re-answering by seeking back is allowed.
- Seeking forward past the furthest point watched is prevented; seeking
  back is free. This is a sponsor design choice, not a Standards
  requirement, and the changelog should say so.
- Keyboard: space toggles play, arrow keys seek within the watched range,
  choices are focusable, Enter submits.
- No confetti. No score. The tone is a colleague's quiet check-in, not a
  game.
- Native `<video>` with controls hidden and a custom minimal control row
  (play/pause, time, mute). No player library.

`/admin/courses/:code/preview` lists the course's lessons and opens the
player for one. A banner says "Preview — nothing is recorded."

## Admin question view
`/admin/courses/:code` gains a Questions section: per lesson, the review
questions in order with their `after_block` and a small indicator for
two-choice ones, and the assessment questions listed separately (read-only,
007 does the rest). Above it, the readiness checklist from
`readiness.check`, rendered as plain lines with block/warn styling.

## Tests
- ingest normalizes 5 review + 3 assessment into 8 questions, 32 choices,
  exactly one correct per question
- a version-2 ingest creates its own questions; version 1's remain
- `required_review_questions`: 0.2→0, 0.4→1, 0.5→2, 0.6→2, 0.8→3, 1.0→3,
  1.2→3, 1.4→4, 2.0→6 (the 5.01.2.1 chart and the above-one-credit rule)
- readiness: a course whose credit needs 3 and has 2 counting review
  questions reports `review_minimum` with both numbers; a two-choice review
  question does not count and produces `review_two_choice`
- grading: correct and incorrect verdicts, feedback returned both ways
- the play payload and the admin question payload contain no `is_correct`
  anywhere (walk the JSON)
- `blocks` rules: non-contiguous refused, last end far from duration
  refused, `after_block` beyond the list refused

## COMPLIANCE.md
Rows for 5.01.2 (review questions and the player as participant
engagement), 5.01.2.1 (placement via measured blocks; minimums; two-choice
exclusion; no passing rate), 5.01.2.2 (verdict always, feedback always). The
5.01.2.1 Gap: "other content reinforcement tools" (simulations, exercises)
are not modeled; only multiple-choice review questions satisfy the floor.

## Acceptance
- `pytest` passes; migration round-trips
- Ingest the exported ASC842-PCX-01 zip (with `blocks`); attach it; the
  Questions section shows 5 review + 3 assessment; readiness shows the
  review count against the required count for the course's credit
- Preview: the video plays, pauses at each of the five review points on the
  right word, the question panel works, wrong answers offer re-watch, and
  the progress bar shows five ticks
- The answer key is absent from every network response the preview makes
  (check the browser's network tab, not just the tests)

## When done
Append the 006 entry. Decisions: questions per package version; in-video
placement; forward-seek prevention as a sponsor choice; no player library.
Known gaps: nothing persisted; assessment not built; other reinforcement
tools not modeled. Add to ROADMAP improvement notes: captions toggle.
Then stop.
