# Decision — The video player's forward-seek lock becomes a ceiling at the next unanswered review question

Recorded: 2026-09-13 (feature 031)
Status: decided
Reverses: the 006 changelog Decision "Forward-seek prevention is a sponsor
design choice, not a Standards requirement (5.01.2.1 sets no such rule), and
is enforced only in the player", and the 023 resolution recorded in
2026-09-01-text-first.md's open question ("relaxed for supplemental clips,
kept for the video-only player"). This is that decision's counterpart for
the video-only player. Does not reverse any compliance decision.

## The decision

The video-only player (`frontend/src/components/Player/Player.jsx`) lets a
participant seek forward and backward freely, with one ceiling: the earliest
review point in the lesson whose question is still unanswered. Reaching that
point — by playback, by a seek, or by the "Forward 15 s" control — pauses and
asks the question exactly as playback always has. Answering moves the
ceiling to the next unanswered point; once every review question in the
lesson is answered, the whole timeline is open.

`lesson_progress.furthest_seconds` is still reported and still drives
resume (to the furthest point or the ceiling, whichever is earlier). It no
longer gates anything in the player.

## Why

006 locked forward seeking at the furthest point watched and recorded it as
a sponsor design choice. 023 relaxed that for supplemental clips in text
courses and kept it for the video-only player as "its own decision". The
sponsor has now made it: forward and backward controls are wanted, and the
one thing the lock actually protected — that no placed review question can
be skipped — is kept by the ceiling.

What the Standards require (2026 Statement, read for 031):

- 5.01.2.1 (printed page 9) — review questions "must be placed throughout
  the program in sufficient intervals to allow the participant the
  opportunity to evaluate the material that needs to be re-studied", with
  the per-credit minimum. Placement is the requirement; the player's job is
  to present each placed question, and the ceiling guarantees each one is
  presented before playback continues past it.
- 5.01.2.2 (printed page 10) — feedback on every review question, at least
  "correct" or "incorrect". Unchanged.
- 6.01 (printed page 10) — the sponsor must "verify individual successful
  program completion for self study … Self-certification of
  attendance/completion alone is not sufficient." Verification is the
  qualified assessment (6.01.2) plus the review-answer record; it is not
  playback behavior, and watch position never reached a completion,
  certificate, or audit record.
- 7.02.6–7.02.7 — Method 2 credit is computed from measured duration and
  word count, not from how a participant moves through the media.

So the ceiling keeps everything the Standards ask for and removes only the
sponsor's stricter reading. It also removes a real cost: a participant who
reloaded could not jump back to where they left off past `furthest_seconds`
without watching again.

## What is not changing

- Which questions are asked, how they are graded, how answers are recorded
  (`review_answers`), the qualified assessment, and the assessment gate
  (`assessment_available`: every pinned review question answered).
- Reader clips (`Reader.jsx`): native controls, no seek handler since 023.
- Re-asking on the way back: crossing an answered review point during
  playback still asks it again (006's behavior; re-answering is allowed).
  Seeks never ask except when they land on the ceiling.
- The 006 in-flight clamp stays on `seeked`, for 006's reason.

## Consequence to know about

`lesson_done` in `backend/app/services/enrollments.py` marks a video lesson
"done" when `furthest_seconds` reaches the duration (display only; nothing
that gates the assessment, records a completion, or reaches a certificate
or the audit bundle reads it). With the ceiling, a participant can reach the
end by seeking once every review question in the lesson is answered, so
"done" for a video lesson now effectively means "every question answered
and the end reached", not "played through". 031 did not change that
derivation; deciding whether it should read from the review record instead,
as it already does for text lessons, is a separate decision.
