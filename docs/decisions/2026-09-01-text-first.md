# Decision — Text-first courses (strategy pivot)

Recorded: 2026-09-01
Status: decided
Supersedes: the video-first content premise implicit in features 001–022 and in
video-tool's design. Does not supersede any compliance decision.

## The decision

superCPE's primary course format becomes **text-first**: a study guide is the
program, short videos are optional supplements that add worked examples and
commentary, and review questions are placed between sections of the text.
Video-only courses remain supported; they stop being the flagship format.

ASC842-PCX is reclassified as the **pipeline validator**. It proved
video-tool → ingestion → review → credit → publish end to end. It may ship
later as a small course or be grown with a study guide; the business is not
measured against it.

## Why

Discovered 2026-09-01 during the first end-to-end authoring run
(first-course-walkthrough.md), by the operator, as a user:

1. **Video is the most expensive medium per credit.** Under Method 2, 50
   minutes of produced video buys 1.0 credit; roughly 9,000 words of text buys
   the same (7.02.6). ASC842-PCX cost four produced lessons and yields 1.8
   credits, ~70% of which comes from the questions, not the video.
2. **The market buys credits per hour of effort.** The dominant self-study
   competitors are text/PDF products with large word counts. A catalog of
   1.8-credit video courses cannot compete on the axis customers actually use.
3. **Text-first fires all three formula terms at once.** Words ÷ 180 (7.02.6)
   + full duration of genuinely additional-learning video (7.02.7) + questions
   × 1.85 including those above minimum (7.02.6). A 60,000-word guide with
   eight 3-minute example videos and 45 questions computes to 8.8 credits.
4. **Two existing gaps get cheaper, not more expensive.** The
   application-blocking 4.05.3 items 2–3 (keyword search, glossary) are
   natural features of a text reader and awkward ones for a video player. The
   005 COMPLIANCE row ("word_count is taken on trust") can close entirely,
   because when the text ships in the package superCPE counts the words
   itself.

## What is not changing

- Method 2 remains the sole credit basis. Method 1 pilot testing stays
  unimplemented (005).
- All publish gates, the 4.02 review requirement, credit snapshotting,
  certificate freezing, enrollment/webhook rules, retention rules — untouched.
- The two-repo split and `docs/course-package.md` as the only interface.
- Question minimums are floors we exceed deliberately, never ceilings we game.
  Word count is real instructional text or it is not counted; the 7.02.5
  exclusions are enforced structurally, not by author honesty.

## Integrity lines (restating, because this pivot is where they get tested)

- A video that narrates the text is **narration**, and its minutes must not be
  counted alongside the words (7.02.7). The package format must make the
  distinction structural.
- Word count includes only body text critical to the stated learning
  objectives. Intro, instructions, bios, TOC, glossary, pre-assessment, and
  appendixes are excluded (7.02.5). Full codification/regulation text goes in
  an excluded appendix; only pertinent excerpts appear in the body.
- Credit is computed from measured inputs. Padding text or questions beyond
  what the content supports is a fabricated 9.02.2(2)(ii) record bearing the
  reviewer's attestation. The reviewer reads the guide.

## Sequence

1. Feature 023 — text-first course packages (contract + ingestion + reader +
   credit). Spec: current-feature.md.
2. Author the first text-first course (topic TBD; ASC 842 expansion is a
   candidate since the research and videos exist).
3. Revisit ASC842-PCX afterward: grow it with a guide, or ship small.

## Open questions (decide during or after 023, not silently)

- Whether the video player's forward-seek lock is retained for supplemental
  videos in text-first courses. Completion is verified by the qualified
  assessment (6.01.2), not watch-time; 5.01.2.1's "sufficient intervals"
  requirement is satisfied by question placement in the text. Leaning: relax
  for supplemental videos, keep question gates. Decide explicitly in the 023
  spec review, record here.
- Pricing model for large-credit courses vs. the current per-course price.
