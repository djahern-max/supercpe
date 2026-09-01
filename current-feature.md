# Feature 023 — Text-first course packages

One feature, three parts, two repos. Part A changes the contract
(`docs/course-package.md`, mirrored in both repos). Part B is superCPE:
ingestion, word count, reader, credit, 4.05.3 surfaces. Part C is video-tool:
authoring and export. Part B can be built against a hand-made fixture package
before Part C exists; do it in that order.

Motivation and the strategy decision are recorded in ROADMAP.md
("Text-first courses (strategy pivot)", 2026-09-01). This spec is the
mechanism only.

## Standards this feature answers to

- **7.02.5** — word count basis: only body text critical to the stated
  learning objectives. Excluded: course introduction, instructions to the
  participant, author biographies, table of contents, glossary, pre-program
  assessment, appendixes of supplementary reference material. Full accounting
  rules/regulations belong in an appendix (excluded); only pertinent excerpts
  in the body (counted).
- **7.02.6** — the formula: [(words ÷ 180) + A/V minutes + (questions ×
  1.85)] ÷ 50, questions counted including those above minimum, rounded down
  per 7.01.
- **7.02.7** — A/V minutes count only if the segment is additional learning,
  i.e. not narration of the text.
- **5.01.2.1** — ≥3 review questions per credit (chart for fifths), placed
  throughout the program at sufficient intervals; true/false does not count.
- **5.01.2.2** — feedback on every review question.
- **6.01.2** — qualified assessment: 70% pass, ≥5 questions per credit (chart
  for fifths), no duplicates of review questions, no true/false; must measure
  ≥75% of learning objectives.
- **4.05.3** — instructional materials must include: (1) overview of topics,
  (2) ability to find information quickly (index or keyword search), (3)
  definition of key terms (glossary or equivalent), (4) navigation
  instructions, (5) review questions with feedback, (6) qualified assessment.
  Items 2 and 3 are currently unbuilt and application-blocking.

## Part A — contract change (`docs/course-package.md`)

### A1. Package kinds

`manifest.json` gains `"kind": "video" | "text"`. Absent means `video`
(every existing package remains valid; ingestion of current zips is
unchanged).

### A2. Text package layout

```
ASC842-GDE-01.zip
  manifest.json
  guide/
    00-front-matter.md      # role: front_matter
    01-overview.md          # role: body
    02-....md               # role: body  (one file per section)
    90-glossary.md          # role: glossary
    91-appendix-a.md        # role: appendix
  media/
    ex-01.mp4               # optional supplemental videos
    ...
  questions.json
```

### A3. Manifest (text kind)

```json
{
  "kind": "text",
  "course_code": "...",
  "lesson_id": "...",
  "version": "v1",
  "title": "...",
  "field_of_study": "...",
  "knowledge_level": "...",
  "prerequisites": "...",
  "advance_preparation": "...",
  "learning_objectives": ["..."],
  "sections": [
    {"id": "sec-01", "file": "guide/01-overview.md", "role": "body",
     "title": "..."},
    {"id": "sec-90", "file": "guide/90-glossary.md", "role": "glossary",
     "title": "Glossary"}
  ],
  "media": [
    {"id": "vid-01", "file": "media/ex-01.mp4",
     "placement": {"after_section": "sec-02"},
     "av_is_additional_learning": true,
     "duration_seconds": null}
  ],
  "glossary_terms": [
    {"term": "...", "definition": "...", "section_id": "sec-90"}
  ]
}
```

Rules the contract states explicitly:

- `role` ∈ `front_matter | body | glossary | appendix`. **Only `body`
  sections enter the word count** (7.02.5). The contract quotes the 7.02.5
  exclusion list verbatim so authors see why.
- `word_count` is **not a manifest field for text packages.** superCPE
  computes it from the body sections at ingestion (closes the 005 trust gap).
  Video-kind packages keep their manifest `word_count` (still trusted; still
  logged as such).
- For text packages, `av_is_additional_learning` must be `true` on every
  media item, and the contract states the 7.02.7 test in one sentence: if the
  video reads the text aloud, it does not belong in a text package. There is
  no narration branch here — a text package's video minutes always count, so
  the attestation that they genuinely add is part of the 4.02 review scope
  (see B6).
- `questions.json` placement for text packages: `{"after_section": "sec-NN"}`
  for review questions (mirrors `after_block`); assessment questions
  unchanged.
- `duration_seconds` on media may be null in the manifest; ffprobe at
  ingestion is authoritative (matches current video behavior).

## Part B — superCPE

### B1. Ingestion

- Accept `kind: "text"`. Validate: every `sections[].file` exists in the zip;
  at least one `body` section; every media `placement.after_section` names a
  real section; every question placement names a real section; markdown
  parses; `glossary_terms` non-empty if the course is to satisfy 4.05.3(3)
  (warn, don't refuse, at ingestion — the publish gate refuses, B7).
- Compute `word_count` = words in `body` sections only, from the shipped
  markdown, after stripping markdown syntax, code fences, and image/link
  URLs. Store per-section counts and the total. Record in the package row
  that the count was **computed from source** (vs. "trusted from manifest"
  for video packages) — this distinction prints in the credit calculation
  record.
- ffprobe every media file for duration, as today.
- The packages table gains kind, per-section word counts, media count.
  The package detail view renders a human summary (kind, body word count,
  sections by role, media with durations, question counts) above the raw
  manifest. (This also resolves the walkthrough finding that word_count was
  visible only inside raw JSON.)

### B2. Credit calculation

- Words term: sum of computed body word counts across attached text lessons ÷
  180. Video-kind lessons contribute their existing (trusted) word_count —
  in practice 0 for narrated video, unchanged.
- A/V term: text-package media always counts (structurally
  additional-learning); video-package behavior unchanged.
- Questions term: unchanged (already counts all questions).
- The plain-text calculation record: per-lesson lines now say either
  `words: N counted (computed from package text, body sections only,
  7.02.5)` or `words: N counted (from manifest, trusted)` — and for A/V,
  `(supplemental, additional learning)` for text-package media. **Fix the
  existing label**: video-kind lessons where the video is the whole program
  currently print "(additional learning)"; they should print "(program is
  the video, 7.02.7)". Cosmetic, but this text lands in the audit bundle.

### B3. Reader surface (participant)

A text course lesson renders as a sequential reader:

- Sections in manifest order. Front matter first (satisfies 4.05.3(4)
  navigation instructions — see B5), body sections gated: a review question
  placed `after_section` must be answered before the next section unlocks.
  Same answer-checking flow, feedback, and no-answer-key-to-browser rule as
  the player (the 006 protections apply verbatim; add the equivalent test).
- Supplemental videos render inline at their placement. **No seek lock on
  supplemental videos.** Rationale recorded here per the ROADMAP open
  question: completion verification is the qualified assessment (6.01.2);
  interval placement of review questions is satisfied by section gating
  (5.01.2.1); the seek lock was a video-first design choice, not a Standards
  requirement, and it is deliberately not carried into the text format. The
  video-only course player keeps its existing behavior in this feature
  (changing it is a separate decision).
- Glossary and appendix sections are reachable at any time from the reader
  chrome (not gated) — they are reference, not required reading, which is
  the same reason they are excluded from the word count.
- Assessment start rule unchanged: refused until all review questions
  answered, naming the unanswered ones.

### B4. Keyword search — 4.05.3(2)

Server-side search endpoint scoped to a single course's text content
(sections of all attached text lessons), available to enrolled participants
and in admin preview. Simple term matching with section-level results and
highlighted snippets is sufficient; the Standard's own example is "an index
or key word search function." Results link into the reader at the section.
Search must not index or return question text (answer-adjacent content stays
out of any payload the browser can query).

### B5. Glossary and navigation — 4.05.3(3), 4.05.3(4)

- Glossary page per course, rendered from `glossary_terms` across attached
  lessons, linked from the reader chrome. Term lookup from within the reader
  (click/tap a term or a glossary button) satisfies "a search function that
  takes a participant to the definition."
- A standard "How this course works" front-matter block (navigation,
  components, completion requirements) is required content for the
  front_matter section; the contract ships a template. Satisfies 4.05.3(4)
  without counting toward credit.
- 4.05.3(1) overview of topics: the body's first section or the description;
  the publish gate checks presence of a section titled/flagged as overview
  OR a course description, whichever the implementation finds cleaner —
  state the choice in the changelog.

### B6. Review scope

The 4.02 content review sign-off text shown to the reviewer gains one line
for text courses: the reviewer attests the supplemental videos constitute
additional learning and not narration of the text (7.02.7), and that
appendix/glossary material is correctly excluded from required reading
(7.02.5). No schema change — the attestation text is versioned the way the
sign-off already is.

### B7. Publish gate additions (accumulating, like all block findings)

For a course with any text lesson:

- refuse if computed body word count is 0
- refuse if no glossary terms exist (4.05.3(3))
- refuse if no front-matter/navigation block exists (4.05.3(4))
- existing gates unchanged (review question minimums per 5.01.2.1's chart,
  assessment minimums per 6.01.2's chart, review staleness, reviewer ≠
  developer, CPA participation, description, price)

Search (B4) is code, not content — no gate needed; its absence is a failed
deploy, not a publishable state.

### B8. Explicitly out of scope for 023

- Changing the video-only player's seek behavior
- Mixed courses beyond what falls out naturally (a course may attach both
  kinds; credit and gates compose per-lesson without special handling)
- Pricing changes
- Migrating ASC842-PCX

## Part C — video-tool

- Author sections as markdown files; `questions.json` gains
  `after_section` placement; export the text-kind zip per Part A.
- Supplemental clips: existing Remotion/ElevenLabs pipeline, exported into
  `media/` with placements.
- Word-count preview at export time using the same counting rules as B1
  (body only, markdown stripped), plus a credit estimate, so authoring
  decisions see the formula the way superCPE will compute it. Label it an
  estimate; superCPE's computation is authoritative.
- Refuse export if any media item lacks `av_is_additional_learning: true`,
  with the 7.02.7 sentence in the error.

## Acceptance criteria

Fixture: a hand-made text package with front matter, 3 body sections, a
glossary (≥5 terms), an appendix, 1 supplemental video, 5 review + 4
assessment questions.

1. Ingesting the fixture computes word_count from body sections only.
   Hand-count one body section; the per-section number matches. Words in
   front matter, glossary, and appendix provably do not move the total
   (re-ingest with 1,000 words added to the appendix as v2; body count
   unchanged).
2. Credit panel shows all three terms nonzero for a course with the fixture
   attached; plain-text record says "computed from package text" and
   arithmetic re-adds by hand.
3. Reader gates: next body section locked until the placed review question
   is answered; glossary and appendix reachable while gated; assessment
   refused with unanswered questions named.
4. Answer-key test (006-equivalent) passes for the reader payloads; search
   endpoint returns no question text.
5. Search finds a term appearing in exactly one section and links to it.
6. Glossary page renders all terms; in-reader lookup reaches a definition.
7. Publish gate: fixture course with glossary_terms emptied refuses naming
   4.05.3(3); with front matter removed refuses naming 4.05.3(4); with all
   content present and review recorded, publishes.
8. Existing video-kind package ingestion, credit, player, and publish are
   unchanged (run the full existing suite; zero modified expectations
   outside the credit-record label fix in B2).
9. Operator-run on production: ingest the fixture, verify the package detail
   summary, verify the credit record wording, delete the draft course.
   (Database is currently disposable; still do the delete to exercise it.)
10. `docs/course-package.md` updated in both repos, identically.

## Changelog note

Record in the 023 entry which option was taken for 4.05.3(1) (B5), and carry
the outstanding 016-date correction if 017's entry has not already done so.
