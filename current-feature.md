# Feature 023a — manifest.json joins the content hash

Small corrective feature from the 2026-09-01 walkthrough (Stage 1) and the
023 contract review. Do this before video-tool 05, so the contract is
mirrored into that repo once, in its final form.

## The finding

Ingest dedup keys on `content_hash`, and the hash covers transcript,
questions, and video (video kind) or sections, questions, and media (text
kind) — **manifest.json is excluded in both definitions**. A re-upload
whose only change is in the manifest is deduplicated as "Already ingested —
nothing was created … unchanged," which is false: it was changed and
ignored.

The manifest is not incidental. Video kind: `word_count` (a credit input),
`field_of_study`, `knowledge_level`, `prerequisites`,
`advance_preparation`, `learning_objectives`, `sources`. Text kind: section
`role`s (a role flip moves the computed word count and therefore the
credit), `glossary_terms`, media placements. Every one of these can change
while the hash stands still.

## The change

1. **Contract** (`docs/course-package.md`): `content_hash` is sha256 over
   the raw bytes of `manifest.json` first, then the existing sequence for
   the kind (video: transcript.md, questions.json, video.mp4; text:
   sections in manifest order, questions.json, media in manifest order).
   One definition sentence per kind, replacing the current ones.

   Chicken-and-egg guard: the hash cannot cover its own field. The
   manifest is hashed with the `content_hash` key absent — state this in
   the contract, and make the exporter compute it that way (video-tool 05
   implements; the fixture factory here does the same).

2. **Ingestion**: recompute per the new definition; the rule number and
   message stay. Stored rows keep their historical hashes — they were
   computed under the definition of their day and remain valid records.
   Consequence, stated in the changelog: the first re-upload of a
   byte-identical old package after this deploys will hash differently and
   create version N+1 once. Harmless (a new version of identical content),
   and on the current disposable database, invisible.

3. **Message accuracy**: with the manifest inside the hash, "unchanged" is
   now literally true on a hash match. No wording change needed — record
   in the changelog that the walkthrough's message-accuracy finding is
   resolved by construction rather than by rewording.

## Acceptance

1. Re-upload of a byte-identical package → 200, created: false, unchanged.
2. Re-upload with one manifest field changed (use a section `role` flip on
   the text fixture, appendix → body) → **201, new version**, and the new
   version's computed word count reflects the flip.
3. Same test on a video-kind fixture with `word_count` changed → 201, new
   version, credit recomputes on a course holding it.
4. The factory and `docs/course-package.md` agree with the implementation;
   the existing suite passes with no other modified expectations.

## Out of scope

- Mirroring the contract into video-tool (that is video-tool 05's first
  step, immediately after this ships).
- Any retro-rehashing of stored packages.
