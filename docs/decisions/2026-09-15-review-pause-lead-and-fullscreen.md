# Decision — Review pauses land 0.3 s before the block boundary, and the player goes full screen as a whole

Recorded: 2026-09-15 (feature 039)
Status: decided
Reverses: nothing. It sits beside 2026-09-13-video-seek-ceiling.md and
keeps that ceiling intact.

## The decision

1. **Pause lead.** A review point's pause time is
   `max(block.start_seconds, block.end_seconds − REVIEW_PAUSE_LEAD_SECONDS)`,
   with `REVIEW_PAUSE_LEAD_SECONDS = 0.3` (ours). It is computed once, where
   the player builds its review points (`frontend/src/components/Player/Player.jsx`).
   The crossing detector, the ceiling, the seek clamp, `handleSeeked`'s
   land-on-ceiling check, resume on load, and resume after Continue all read
   that time and nothing else. The tick on the bar stays at `end_seconds`.
   At bar scale a 0.3 s difference can't be seen, and the tick marks where
   the block ends.
2. **Frame-accurate detection.** While playing, the detector runs on every
   video frame (`requestVideoFrameCallback`, else `requestAnimationFrame`).
   `timeupdate` still updates the furthest point and the time display, and
   runs the same detector as a backstop for when frames are not delivered.
3. **Full screen is the player wrapper.** A "Full screen" control calls
   `requestFullscreen()` on the element that holds the video, the controls,
   and the question panel, never on the `<video>`. It is offered only when
   `document.fullscreenEnabled` is true. There is no `webkitEnterFullscreen`
   fallback, so iPhone Safari has no full-screen control.

## Why

**The lead is inside the silence by construction.** `end_seconds` is where
the next block's MP3 begins. video-tool's `generate` appends 0.6 s of
silence to the end of every block, and ElevenLabs puts almost none at the
start of a file. So the silence at a boundary sits almost entirely *before*
`end_seconds`. `ffmpeg silencedetect` on GPT-06's exported MP4 confirmed
this: every boundary had at least 0.5 s of silence before `end_seconds` and
only 0.07–0.19 s after it. A detector that reacts after `end_seconds`
is already into the next word. `timeupdate` fires only every 15–250 ms,
so it usually was. Any lead under 0.6 s pauses inside the tail. 0.3 s
leaves margin either side, and resuming from the pause time gives the next
word 0.3 s of silence before it.

**One pause time.** If the detector paused at 29.7 s but the ceiling
still sat at 30 s, a seek could land between them and play into the next
word, or skip the ask. Using one derived time everywhere means
the paths cannot disagree.

**Full screen must not open a way past a question.** The 031 ceiling is
what guarantees every placed question is presented (5.01.2.1). iOS's native
video player, which `webkitEnterFullscreen` opens, has its own scrubber that
this component cannot clamp. Taking the wrapper full screen keeps every seek
inside the player. An iPhone user without a full-screen control is the
lesser cost. `playsInline` was already set, so pressing Play on iOS does not
open the native player either.

Standards read for 039 (2026 Statement, printed page 9):

- 5.01.2: examples of participant engagement in self study, including
  content reinforcement tools "as required by 5.01.2.1, such as review
  questions". Nothing about when a player stops.
- 5.01.2.1: review questions "must be placed throughout the program in
  sufficient intervals". Placement is `after_block` against measured
  `video.blocks` (contract rule 18) and does not change. Pausing 0.3 s
  earlier, inside the same inter-block silence, is a presentation detail
  and a sponsor decision, not a Standards requirement.

## What is not changing

- Which questions are asked, where they are placed, how they are graded,
  what is recorded, and the assessment gate.
- Re-asking: every crossing asks. The point just asked is not re-asked on
  resume, because the detector already stands at its pause time. It is asked
  again once the playhead goes back before it (seek back, Rewind, Re-watch).
- Re-watch still seeks to the block's `start_seconds`.
- Reader clips (`Reader.jsx`) keep native controls.

## Consequences to know about

- The lead assumes video-tool keeps a per-block tail of at least 0.3 s.
  `TAIL_SECONDS` lives in video-tool and nothing in superCPE checks it. If
  the tail ever shrinks below the lead, pauses would clip the end of a
  block's last word instead of the start of the next one.
- iPhone users have no full-screen path.
