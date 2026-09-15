# Feature 035 — HTML comments leak into the reader and search

## Goal

Section Markdown containing HTML comments (e.g. `<!-- index: 9#1, 9#2; 4#3 attributed -->`)
currently shows the comment as literal text in the participant reader. Comments are
authoring annotations, not required reading. Drop them everywhere a participant or the
credit calculation sees section text, while keeping all other raw HTML escaped.

## Standards touched

- **7.02.6** — Method 2 divides "the word count for the text of the required reading"
  by 180. An HTML comment is not required reading, so it must never be counted.
- No change to 7.02.7 (A/V minutes) or the question term.

## In scope

1. Report current behavior (before changing anything) for:
   - the component that renders section Markdown in the reader;
   - the search index builder and the search snippet builder;
   - the section word counter used for credit measurement;
   - any other place section or question Markdown is rendered (glossary, review
     question stems/explanations, admin review/preview pages).
   For each: does it render raw HTML, escape it, or skip it? Are comments visible,
   indexed, or counted?
2. One canonical backend function (e.g. `strip_html_comments(md: str) -> str`) that
   removes `<!-- ... -->` comments, including multi-line ones.
3. Apply it to: the reader section payload, the search index input, snippet
   generation, and the word counter.
4. Frontend renderer: drop comment nodes defensively so a comment can never render
   even if one reaches the client. Raw HTML otherwise stays escaped — do not enable
   raw-HTML rendering (no `rehype-raw` or equivalent).
5. One sentence in `docs/course-package.md`: HTML comments are permitted in section
   Markdown and are ignored by superCPE (not rendered, indexed, or counted).

## Out of scope

- Changing stored package source or the 023a content hash. Stripping happens at
  read/index/measure time only; stored Markdown is untouched.
- Any change to video-tool (it may keep emitting comments).
- Interpreting the comment contents (the `index:` annotations are not parsed here).
- Rendering any other raw HTML.

## Rules for the stripper

- Comments inside fenced code blocks and inline code are content, not comments:
  preserve them (and count their words).
- An unclosed `<!--` is not a comment: leave it as text (escaped on render).
- Stripping must not merge adjacent words (replace with nothing only where
  whitespace already separates; otherwise a single space).

## Locators

Report the actual paths in the step-1 findings. Starting points: reader section
component under `frontend/src/`, search/snippet code and word-count code under
`backend/app/` (023 text-package ingestion and search).

## Data model

No migration expected. If the search index or word count is **persisted** at ingest
(stored column, tsvector, or measured credit on a course version), say so in the
findings and do not add a migration or backfill without flagging it first.
Pre-launch, re-ingesting ATO to refresh stored values is acceptable.

## Tasks

1. Findings report (step 1) — stop and include it in the final summary.
2. Implement `strip_html_comments` with unit tests.
3. Wire it into reader payload, search index, snippets, word count.
4. Frontend defensive guard in the renderer.
5. `docs/course-package.md` sentence.
6. COMPLIANCE.md row update.

## Tests

Backend:
- Stripper: single-line, multi-line, multiple comments, comment adjacent to words,
  comment in fenced code (preserved), comment in inline code (preserved), unclosed
  `<!--` (unchanged).
- Reader payload for a section containing `<!-- index: 9#1, 9#2; 4#3 attributed -->`
  contains no `<!--`.
- Search: querying a word that appears only inside the comment (e.g. `attributed`)
  returns no hit for that section; snippets for that section never contain `<!--`
  or comment text.
- Word count: the section with the comment counts exactly the same as the identical
  section with the comment removed.
- Raw HTML other than comments (e.g. `<b>x</b>`, `<script>`) is still escaped, not
  rendered.

Frontend:
- Renderer given Markdown with a comment renders no comment text.
- Renderer given `<script>alert(1)</script>` shows it escaped (no element created).

## Word count — read carefully

The requirement is **"comments are never counted"**, not "the number never changes."
- If findings show the counter already excluded comments: confirm the ATO section
  counts are identical before and after, and say so.
- If the counter was counting comment text: the old count was wrong under 7.02.6.
  Report before/after counts per affected section and the resulting credit change.
  Do not preserve the wrong number. Record it in the changelog under Decisions as a
  measurement correction.

## COMPLIANCE.md rows

- 7.02.6: add that the word count excludes HTML comments (authoring annotations are
  not required reading); cite this feature.

## Acceptance

1. Findings report delivered.
2. All tests above pass; pyflakes, oxlint, and both suites green.
3. Locally, an ATO section containing a comment shows no comment text in the reader.
4. Searching `attributed` returns no ATO section hit sourced from a comment.
5. Word-count result stated per "Word count — read carefully."
6. Operator-only (list under Known gaps if not run): deploy, re-ingest ATO on
   production if values are persisted, browser check of the reader on supercpe.com.

## When done

Append a CHANGELOG entry numbered 035 in the existing format (What changed /
Standards touched / Decisions / Known gaps). Include the findings summary and the
word-count outcome.
