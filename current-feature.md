# Current Feature

## Feature 031 — Free seeking on the video player, up to the next unanswered review question

> Confirm 031 against the last entry in `CHANGELOG.md` before starting. 030a is the last entry as of this writing.

## Goal

The video-only player (`frontend/src/components/Player/Player.jsx`) lets a participant seek forward and backward freely, with one ceiling: the earliest review point in the lesson whose question is still unanswered. Reaching that point — by playback, by a forward seek, or by the new "Forward 15 s" button — pauses and asks the question, exactly as playback does today. Once every review question in the lesson is answered, the whole timeline is open.

Nothing about which questions are asked, how they are graded, how answers are recorded, or how lesson completion is derived changes.

## Why

006 built a forward-seek lock keyed on the furthest point watched and recorded it as "a sponsor design choice, not a Standards requirement (5.01.2.1 sets no such rule)." 023a dropped the lock on reader clips for that reason and left the video-only player's lock as "its own decision." 027 added "Rewind 15 s" and pinned the forward refusal with a test. This feature is that decision, made: the sponsor wants forward and backward controls, and wants the thing the lock actually protected — that no review question can be skipped — kept.

What the Standards require, from the 2026 Statement:

- 5.01.2.1 — review questions "must be placed throughout the program in sufficient intervals to allow the participant the opportunity to evaluate the material that needs to be re-studied," with the per-credit minimum. Placement is the requirement; the player's job is to present each placed question.
- 5.01.2.2 — feedback on each review question, at minimum "correct" or "incorrect." Unchanged.
- 6.01 — the sponsor must "verify individual successful program completion for self study … Self-certification of attendance/completion alone is not sufficient." Verification is the qualified assessment (6.01.2) plus the review-answer record; it is not playback behavior.
- 7.02.6–7.02.7 — Method 2 credit is computed from the measured duration and word count, not from how a participant moves through the media. Seeking does not change the credit claim.

So the ceiling-at-next-unanswered-question rule keeps everything the Standards ask for and removes only the sponsor's stricter reading. It also removes a real usability cost: a participant who reloads or returns later cannot today jump to where they left off past `furthest_seconds` without watching again.

## Read first

- `CLAUDE.md`
- `CHANGELOG.md` entries 006 (player design, in-flight-seek clamp on `seeked`), 010 (`lesson_progress.furthest_seconds`, `review_answers`), 023a (the supplemental-clip decision), 027 (Rewind 15 s, end panel, and the known gap that the video play payload carries no `answered` flag)
- `COMPLIANCE.md` rows for 5.01.2, 5.01.2.1, 5.01.2.2, 6.01
- `docs/decisions/` — find where 023a recorded the supplemental-clip decision; this feature records its counterpart there
- 5.01.2.1, 5.01.2.2, and 6.01 in the 2026 Statement PDF before citing any of them. Do not cite from memory.

## Task 0 — recon, answered in the changelog before code is written

1. **Review points.** Confirm how the player derives each review point's timestamp today (`after_block` → measured `video.blocks[].end_seconds`) and where that list lives in component state. Name the variable.
2. **Answered state.** Confirm that the participant play payload (the route behind `/my/courses/:id/lessons/:packageId`) carries no per-question `answered` flag, and that the reader payload's `questions[]` does. Name the reader field and the serializer so the video payload can match it. Confirm what `review_answers` rows exist to derive it from.
3. **Preview identity.** Confirm whether admin/reviewer preview review answers are persisted (007's `X-Preview-Id`) or held in component state only. The ceiling rule must work in both the enrollment and preview paths; say which source each uses.
4. **`furthest_seconds`.** List every reader of `lesson_progress.furthest_seconds` and of the player's `furthest` state. Confirm whether lesson `done` derives from it or from `review_answered == review_total`. This feature must not change what `done` means; if `furthest` feeds it, stop and report.
5. **The pinned refusal.** Name the 027 test in `Player.test.jsx` that pins the forward-seek refusal. It is replaced, not deleted silently — the new test asserts the new rule.
6. **The unused `furthest` state variable** oxlint warned about in 027. Say whether it goes away as a consequence of this feature or stays.

## In scope

- Play payload: each review question in the video play payload gains `answered: bool`, derived the same way the reader payload derives it (enrollment path) or from whatever the preview path already holds (preview path). If the preview path has no persistence, `answered` is `false` on load and tracked in state, which is the behavior today.
- Player seek rule: replace the `[0, furthest]` clamp with `[0, ceiling]`, where `ceiling` is the timestamp of the earliest review point whose question is unanswered, or the media duration when none remain. A seek that lands on `ceiling` pauses and asks that question, the same code path playback uses when `currentTime` reaches a review point. The in-flight clamp stays on `seeked` (006's reason still holds).
- Answering a question advances `ceiling` to the next unanswered review point. A wrong answer's "Re-watch this section" link still seeks to the block start and resumes; that is a backward seek and is unaffected.
- "Forward 15 s" button (`FORWARD_SECONDS`, same constant pattern as `REWIND_SECONDS`), placed beside Rewind 15 s. Clamped to `ceiling` like any seek.
- Arrow keys seek within `[0, ceiling]` instead of the watched range.
- Progress bar: clicking anywhere in `[0, ceiling]` seeks there. The ticks at review points stay. Answered review points and unanswered ones should be visually distinct if the bar already has a style hook for it; if that needs new design work, leave the ticks as they are and note it under Known gaps.
- `furthest_seconds` keeps being reported for resume. It no longer gates anything in the player. Resume on load still seeks to `min(furthest_seconds, ceiling)`.
- 027's end panel behavior is unchanged: on `ended` with unanswered questions, the remaining questions are asked in place. With the ceiling rule this is only reachable when `ceiling == duration`, i.e. no unanswered questions, so the panel's "remaining questions" branch becomes dead for a participant who cannot skip. Keep it — a reload mid-question can still land there, and 027 documents that case. Say so in the changelog.
- Update `COMPLIANCE.md` rows for 5.01.2 and 5.01.2.1 where they describe the player's forward lock; the "Notes" column records that forward seeking is open up to the next unanswered review question as of 031.
- Record the decision in `docs/decisions/` alongside 023a's, and in the changelog's Decisions.

## Out of scope

- Reader clips (`Reader.jsx`). They have native controls and no seek handler since 023a; nothing changes.
- The qualified assessment, `review_answers` schema, grading, feedback wording, or verdicts.
- What lesson `done` means, or any change to `lesson_progress` columns.
- Skipping to the next review point as a control, playback speed, captions, or a player library.
- Any change to how review points are placed (`after_block`, contract rule 18 in `backend/app/services/packages.py`).
- Re-asking already-answered questions on seek-back. Seeking back past an answered review point plays through it without re-asking (today's behavior).
- Ingest, credit, readiness, or video-tool.

## Locators

- `frontend/src/components/Player/Player.jsx` — `seekTo`, `handleSeeked`, `REWIND_SECONDS`, the review-point pause, the progress bar, keyboard handler
- `frontend/src/components/Player/Player.test.jsx` — backward seek, rewind, the pinned forward refusal
- `frontend/src/pages/MyLesson.jsx` (or wherever the enrollment play payload is fetched) and the admin/reviewer preview page
- Backend: the play-payload route and serializer for video lessons (Task 0 names it); the reader's `answered` derivation to copy from; `review_answers` model from 010
- `backend/tests/test_player.py`
- `COMPLIANCE.md`, `docs/decisions/`, `CHANGELOG.md`

## Data model

No migration. One serializer change: `answered: bool` on each question in the video play payload, present in both the enrollment and preview responses (preview: whatever the recon found — persisted or `false`).

## Tasks

1. Task 0 recon; write the answers into the changelog draft first.
2. Backend: add `answered` to the video play payload for both paths. One test per path in `test_player.py`: enrollment with one `review_answers` row → that question `true`, the rest `false`; preview → the recon's answer.
3. Player: compute `ceiling` from the review-point list and answered state; replace the furthest clamp in `seekTo`, `handleSeeked`, the bar click handler, and the arrow-key handler with the ceiling clamp; ensure a seek that lands on `ceiling` enters the question state.
4. Player: `FORWARD_SECONDS` and the "Forward 15 s" button.
5. Player: answering a question recomputes `ceiling`; the wrong-answer re-watch link is verified as a backward seek.
6. Resume on load: `min(furthest_seconds, ceiling)`.
7. Replace the 027 forward-refusal test with the tests below.
8. `COMPLIANCE.md` rows, `docs/decisions/` entry, changelog.
9. pyflakes, oxlint, both suites.

## Tests

Frontend (`Player.test.jsx`):
- Forward seek past the first unanswered review point is clamped to that point and the question renders.
- Forward seek within `[0, ceiling]` is honored, including past `furthest`.
- Forward 15 s from `ceiling - 5` lands on `ceiling` and asks; from earlier lands 15 s later and keeps playing.
- After answering the first question, a forward seek past its review point is honored and clamps at the second unanswered point.
- With every question answered (`answered: true` on load), a seek to `duration - 1` is honored.
- Load with `answered` flags and `furthest_seconds` past `ceiling`: resume lands on `ceiling` and asks.
- Wrong answer → "Re-watch this section" seeks to block start and resumes (existing test, kept).
- Backward seek and Rewind 15 s (existing tests, kept).

Backend (`test_player.py`):
- Enrollment play payload carries `answered` per question, derived from `review_answers`.
- Preview play payload carries `answered` (value per recon).
- Existing grading and verdict tests unchanged.

## COMPLIANCE.md rows

Edit the Notes of the existing rows, do not add new ones:

| Para | Change to Notes |
|---|---|
| 5.01.2 | Player: seeking is open in both directions up to the earliest unanswered review point (031); each placed question is still asked in place before playback continues past it. |
| 5.01.2.1 | Placement is unchanged. Add: "The 006 forward lock keyed on furthest-watched was a sponsor choice beyond this paragraph and was replaced in 031 by a ceiling at the next unanswered review question; the paragraph's requirement — every placed question presented — is what the ceiling enforces." |
| 6.01 | Add: completion verification is the review-answer record plus the qualified assessment; playback position never was and is not a completion signal. |

## Acceptance

Locally runnable:
1. Both suites green; pyflakes and oxlint show only warnings recorded in 030a or earlier.
2. Admin preview of a video lesson with two review points: drag the bar past the first tick → pauses at the tick, question appears; answer; drag past the second tick → pauses there; answer; drag to the end → honored. Rewind and Forward 15 s behave as tested.
3. Reload the enrollment lesson mid-lesson: resume lands no further than the first unanswered review point.

Operator, listed under Known gaps as "not yet run by the operator":
4. Same walkthrough on production with the ATO video lesson after deploy.

## When done

Append the 031 changelog entry with Task 0 answers, what was built, verification table, Known gaps, and the Decisions section naming this as the reversal of 006's lock and the counterpart of 023a's reader-clip decision. Report, do not build, anything found out of scope — in particular any dependency of lesson `done` on `furthest_seconds`.
