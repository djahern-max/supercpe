# Current Feature

## Feature 036 — Review pauses land in the silence, and the player goes full screen

> Confirm 036 against the last entry in `CHANGELOG.md` before starting. 035 was the last entry seen when this was drafted.

## Goal

1. The video player pauses for a review question inside the silence between narrated blocks, and resumes without clipping the next word.
2. A "Full screen" control puts the whole player (video, controls, question panel) into full screen, so the slides are readable on a phone.

Nothing about which questions are asked, where they are placed, how they are graded, or what is recorded changes.

## Why

**Pause timing.** On GPT-06 the player stops after the narrator has already started the next word. The package is not at fault. `ffmpeg silencedetect` on the exported MP4 shows every `video.blocks[].end_seconds` inside a silence. Every boundary has at least 0.5 s of silence before `end_seconds` and only 0.07–0.19 s after it.

That asymmetry comes from how the audio is made:
- `end_seconds` is where the next block's MP3 begins.
- video-tool's `generate` appends 0.6 s of silence to the end of every block.
- ElevenLabs puts almost none at the start of a file.

A detector that reacts after `end_seconds` has passed will usually be into the next word. `timeupdate` fires only every 15–250 ms, so it often is.

The fix is to pause a fixed lead before `end_seconds`. Any lead under 0.6 s is inside the silence by construction. Use 0.3 s.

**Full screen.** Slides are rendered into a 1920-wide MP4, with type sized to be legible at half width (video-tool entry 31). At a phone's ~400 px the frame is about one-fifth scale, and no player setting recovers that. Full screen in landscape recovers most of it. Render quality itself is a video-tool spec, not this one.

## Standards

Read 5.01.2 and 5.01.2.1 in the 2026 Statement PDF before writing the changelog. Cite them from the PDF, not from this spec.

- **5.01.2.1** requires review questions "placed throughout the program in sufficient intervals." Placement stays `after_block` against measured `video.blocks` (contract rule 18).
  - Pausing 0.3 s early, inside the same inter-block silence, is a presentation detail of when the player stops. It is not a placement change.
  - Record this as a sponsor decision, not a Standards requirement.
- **Full screen must not create a way past a question.** The 031 ceiling is what guarantees each placed question is presented. A native full-screen video player (iOS `webkitEnterFullscreen`) has its own scrubber and would bypass it. That path is refused below.

Neither change touches a retained record, credit, or anything under 9.02.

## In scope

- `REVIEW_PAUSE_LEAD_SECONDS` and a single derived pause time per review point
- Frame-accurate detection near a pause point
- Resume-after-Continue behavior at the shifted point
- A full-screen toggle on the player wrapper, with the iOS native-player path excluded
- `playsInline` on the `<video>` element if not already present
- Tests, a COMPLIANCE.md Notes edit, a `docs/decisions/` entry, and the changelog

## Out of scope

- Hiding or restyling the review ticks. They stay: 006's brief, and they explain the 031 ceiling.
- Anything in video-tool, the package contract, ingest, or readiness, including a silence-alignment check at ingest
- Reader clips (`Reader.jsx`), which keep native controls
- Captions, playback speed, keyboard shortcut for full screen, player library
- Rendering slides as HTML in the browser
- Any backend change

## Locators

- `frontend/src/components/Player/Player.jsx`: the crossing detector, `askQuestions(points)`, the ceiling computation, `seekTo`, `handleSeeked`, `SEEK_TOLERANCE_SECONDS`, `REWIND_SECONDS`, `FORWARD_SECONDS`, the "Re-watch this section" handler, the resume on `loadedmetadata`, the control row
- `frontend/src/components/Player/Player.module.css` (or wherever the player's styles live)
- `frontend/src/components/Player/Player.test.jsx`
- `COMPLIANCE.md`: the 5.01.2 and 5.01.2.1 rows (Notes only; no new rows)
- `docs/decisions/2026-09-13-video-seek-ceiling.md`, which the new decision sits beside

## Data model

None. No migration, no serializer change.

## Tasks

### 0. Recon

Write the answers into the changelog draft first.

1. Which event drives the crossing detector today: `timeupdate`, a timer, or something else? Quote the condition it tests (e.g. `prev < p && cur >= p`).
2. After Continue, where does playback resume? How does the code avoid re-asking the question it just asked?
3. Where is the ceiling compared against `currentTime`? List every site, so step 1 below changes all of them.
4. Is `playsInline` set on the `<video>`?

### 1. One pause time per review point

- Add `REVIEW_PAUSE_LEAD_SECONDS = 0.3` beside `REWIND_SECONDS`.
- Comment it: under `generate`'s 0.6 s per-block tail, so inside the inter-block silence by construction. Name GPT-06's measured margins as the evidence.
- Each review point's pause time is `max(block.start_seconds, block.end_seconds - REVIEW_PAUSE_LEAD_SECONDS)`.
- Compute it once, where review points are built. Every consumer uses it and nothing else reads `end_seconds` for pausing:
  - the crossing detector
  - the ceiling
  - the seek clamp
  - `handleSeeked`'s land-on-ceiling check
  - resume
- The tick position may keep using `end_seconds`. A 0.3 s difference is invisible on the bar. Say which you chose in the changelog.

### 2. Frame-accurate detection

- While playing, check `currentTime` against the next pause time on every video frame:
  - use `video.requestVideoFrameCallback` where available
  - otherwise use `requestAnimationFrame`
- Cancel the callback on pause, on unmount, and when no unanswered-or-askable point remains ahead.
- `timeupdate` keeps doing what it does for `furthest_seconds` and the time display.
- On crossing, the detector calls `pause()` first, then `askQuestions(points)`, as today.

### 3. Resume after Continue

- Playback resumes from the pause time.
- The next word is heard from its start, with 0.3 s of silence before it.
- The point just asked is not re-asked on that resume. It is asked again only after the playhead has gone back before it (seek back, Rewind, or Re-watch). That preserves 031's "every crossing asks" behavior.

### 4. Full screen

- Add a "Full screen" button at the end of the control row. It reads "Exit full screen" while active.
- Call `requestFullscreen()` on the player wrapper element: video, control row, and question panel together. Never call it on the `<video>` element.
- Show the button only when `document.fullscreenEnabled` is true. On iPhone Safari this hides it.
  - Do not fall back to `webkitEnterFullscreen`. The native player's scrubber bypasses the ceiling.
  - Record this in Decisions.
- After entering, try `screen.orientation.lock("landscape")` and ignore any rejection.
- Track state from `fullscreenchange`, so Escape or the OS gesture updates the label.
- In `:fullscreen`:
  - the wrapper fills the screen on the existing dark/neutral ground
  - the video fills the space above the control row, with `object-fit: contain`
  - the question panel still overlays the video area at the same width, as 006 specifies
- Set `playsInline` on the `<video>` if recon found it missing, so iOS does not take the video into its native full-screen player on play.

### 5. Docs and gates

- `COMPLIANCE.md` Notes on 5.01.2 and 5.01.2.1: questions are asked at `end_seconds − 0.3 s`, inside the inter-block silence, as a presentation choice with placement unchanged. Full screen runs through the same player, so the ceiling still holds.
- `docs/decisions/2026-09-15-review-pause-lead-and-fullscreen.md`
- pyflakes, oxlint, and both suites

## Tests

`Player.test.jsx`. jsdom has no `requestVideoFrameCallback`, so drive the `requestAnimationFrame` fallback with a mocked clock and a stubbed `currentTime`.

- A review point with `end_seconds` 30 pauses when `currentTime` reaches 29.7 and asks. It does not wait for a `timeupdate` at or after 30.
- A block shorter than the lead pauses at its `start_seconds`, never before it.
- After Continue at 29.7, playback resumes at 29.7, and advancing to 31 does not re-ask.
- Seeking back to 20 and playing through 29.7 asks again.
- The ceiling clamp uses the pause time. A forward seek to 60 with the point unanswered lands on 29.7 and asks.
- Forward 15 s from 20 lands on 29.7 and asks.
- "Re-watch this section" still seeks to the block's `start_seconds`.
- Resume on load with `furthest_seconds` past an unanswered point lands on its pause time and asks.
- Full screen, with `requestFullscreen`, `document.fullscreenEnabled`, and `fullscreenchange` mocked:
  - the button is absent when `fullscreenEnabled` is false
  - clicking calls `requestFullscreen` on the wrapper, not the video
  - the label flips on `fullscreenchange`
  - a rejected `screen.orientation.lock` does not throw
- The existing 031 and 027 player tests pass, with expected times updated only where they asserted a pause at `end_seconds`. List each such edit in the changelog.

## Acceptance

1. Lint and both suites pass.
2. **Local, GPT-06 preview.** At each of the three review points, the question appears after the narrator's last word and before the next. After Continue, the next block's first word is heard whole.
3. **Local, forward seek past an unanswered point.** It lands on the point and asks, and the next word is not heard first.
4. **Desktop Chrome and Safari.** Full screen shows video, controls, and the question panel. A question asked while in full screen is answerable there. Escape exits and the label updates.
5. **Android phone, if available.** Full screen enters landscape where the browser allows it.
6. **iPhone.** No Full screen button. Pressing Play does not open the native player.
7. **Production.** Deploy and repeat 2 and 4. Operator-only; list under Known gaps as not yet run if not done.

## When done

Append the 036 entry.
- **Standards touched:** 5.01.2 and 5.01.2.1, read from the PDF.
- **Decisions:**
  - the 0.3 s lead and why it is inside the silence by construction
  - pause time as the single source for ceiling and detection
  - wrapper-element full screen, and the refusal of iOS native full screen because it bypasses the ceiling
- **Known gaps:**
  - iPhone users have no full-screen path
  - the lead assumes video-tool keeps a tail of at least 0.3 s. `TAIL_SECONDS` lives in video-tool and nothing here checks it.

Then stop.
