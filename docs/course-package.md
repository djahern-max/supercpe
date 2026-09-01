# Course package contract, v1

The only interface between `video-tool` (local) and `superCPE` (deployed).
video-tool writes it; superCPE reads it. Neither repo imports from the other.

A package is a directory (or zip of one) for **one lesson**:

    <lesson-id>/
      manifest.json
      video.mp4
      transcript.md
      questions.json

Courses are assembled in superCPE from one or more lesson packages. The course
is the credit-bearing unit (a lesson on its own may be below the 0.2 minimum).

## manifest.json

```json
{
  "package_version": 1,
  "lesson_id": "ASC606-CON-01",
  "course_code": "ASC842-PCX",
  "position": 1,
  "title": "Why Percentage of Completion Is No Longer a Method",
  "content_hash": "sha256, see definition below",

  "video": {
    "duration_seconds": 486,
    "duration_source": "measured",
    "measured_at": "2026-08-20T14:02:11Z",
    "narration_blocks": 7,
    "tts_provider": "elevenlabs",
    "tts_voice_id": "HKFOb9iktHA85uKXydRT",
    "tts_model": "eleven_multilingual_v2",
    "blocks": [
      { "id": "block-01", "start_seconds": 8.000, "end_seconds": 65.120 },
      { "id": "block-02", "start_seconds": 65.120, "end_seconds": 121.960 }
    ]
  },

  "learning_objectives": [
    { "id": "lo-1", "text": "Distinguish a method from an output measure under ASC 606" }
  ],
  "field_of_study": "Accounting",
  "knowledge_level": "Intermediate",
  "prerequisites": "Basic familiarity with ASC 606",
  "advance_preparation": "None",

  "sources": [
    { "citation": "ASC 606-10-25-27", "role": "primary" }
  ],

  "author": { "name": "...", "credentials": "CPA", "license_jurisdiction": "NH",
              "license_number": "..." },

  "word_count": 0,
  "av_is_additional_learning": true
}
```

### Rules superCPE enforces on ingest

- `package_version` must be 1. Anything else is rejected with a message naming
  the version, not silently coerced.
- `course_code` and `position` are required. `course_code` names the course the
  lesson was exported for; superCPE refuses to attach a lesson to a course with
  a different code. `position` is the lesson's order within that course, a
  positive integer, unique within the course. video-tool writes both.
- `video.duration_source` must be `"measured"`. video-tool must refuse to export
  while its `usingEstimates` flag is true. superCPE rejects any other value.
  This is how 7.02.7's "actual audio/video duration time" is guaranteed: the
  number is never typed in superCPE, and the tool that produced it attests it
  was measured from the rendered narration.
- `duration_seconds` must match the uploaded mp4 within 1 second, checked with
  ffprobe on the server. A mismatch is rejected, not warned.
- `video.blocks` records where each narrated block starts and ends in the
  video, in seconds: one entry per narrated block, in playback order, ids
  matching the `## <block id>` headings in `transcript.md`.
- `start_seconds` of the first entry is the title sheet's duration; each
  subsequent `start_seconds` equals the previous `end_seconds`; the last
  `end_seconds` equals `duration_seconds` within 1 second.
- Values come from measured audio; a package whose `duration_source` is
  measured must not carry estimated block timings.
- `questions.json` `after_block` refers to the 1-based index into this list.
- `content_hash` is the lowercase hex sha256 digest of the concatenation of
  the **canonical manifest bytes** (defined below), then the raw bytes of
  `transcript.md`, then `questions.json`, then `video.mp4`, in exactly that
  order. It is recomputed on ingest and must match. A re-upload with the same
  hash is a no-op; a different hash creates a new lesson version and marks the
  course's credit and review as stale.
- `word_count` is the count of text learning material a participant must
  *read* (7.02.5). For an all-video lesson it is 0 and stays 0. The transcript
  is not reading material and is never counted; it is the transcript of record.
- `field_of_study` must be a value from `docs/2024-Fields-of-Study.pdf`.
- `knowledge_level` must be one of the Standards' defined levels (Basic,
  Intermediate, Advanced, Overview, Update).
- `learning_objectives` is a non-empty array of `{ "id", "text" }` objects.
  Ids must be unique within the manifest; `questions.json` references them
  through `objective_ids`.

### The canonical manifest bytes

The manifest is part of the content the hash covers, for both kinds. It
has to be: `word_count` is a credit input, a section `role` decides
whether words are counted at all, and `field_of_study`,
`knowledge_level`, `prerequisites`, `advance_preparation`,
`learning_objectives`, `sources`, `glossary_terms` and media placements
can all change in a re-export while every other file in the zip stays
byte-identical. If the manifest were outside the hash, such a re-upload
would be deduplicated and the change silently discarded.

Two consequences follow, and both sides implement them identically:

1. **The hash cannot cover its own field.** The `content_hash` key is
   removed from the manifest object before hashing. The exporter
   therefore computes the digest first and writes the finished
   `manifest.json` second.
2. **What is hashed is the parsed object, not the file's bytes.** Because
   the exporter must hash before it can finish writing the file, the two
   repos can only agree on a canonical serialization of the manifest:

       json.dumps(manifest_without_content_hash,
                  sort_keys=True,
                  separators=(",", ":"),
                  ensure_ascii=False).encode("utf-8")

   Keys sorted, no spaces after `,` or `:`, UTF-8, non-ASCII characters
   left as themselves. Indentation and key order in the written file are
   free and move nothing.

Everything after the manifest in the digest is the raw bytes of the files
themselves, in the order each kind defines.

## transcript.md

The narration of record, reveal markers stripped, one block per heading. This
is retained under 9.02.1(8) "program materials" and is what a content reviewer
signs off on under 4.01.1. It is not shown to participants by default.

## questions.json

```json
[
  {
    "id": "q-01",
    "kind": "review",
    "after_block": 3,
    "stem": "...",
    "choices": [ {"id": "a", "text": "..."}, ... ],
    "correct": "b",
    "feedback": "Principles-based feedback per 5.01.2.2: reinforces the
                 concept, names the gap, points to the block to re-study.",
    "objective_ids": ["lo-1"]
  },
  {
    "id": "q-08",
    "kind": "assessment",
    "stem": "...",
    "choices": [ ...at least 3, per 6.01.2 forced-choice prohibition... ],
    "correct": "c",
    "feedback": "...",
    "objective_ids": ["lo-2"]
  }
]
```

### Rules

- `kind` is `review` or `assessment`. Nothing else.
- Review questions carry `after_block` so superCPE can place them between
  segments (5.01.2.1 "throughout the program in sufficient intervals").
- Assessment questions must have at least 3 choices. Review questions at least 2.
- Every question maps to at least one learning objective by id. A question
  mapping to nothing is rejected.
- Both kinds count toward the 1.85-minute term of the credit formula (7.02.6),
  including review questions above the minimum. superCPE computes credit from
  the total; the manifest does not carry a credit figure, because credit is a
  course-level number and video-tool does not know the course.

## What the package deliberately does not contain

- CPE credit. Computed in superCPE at the course level.
- Pilot test data. superCPE uses method 2 (word count formula). Method 1 is not
  built in either repo.
- Reviewer identity or sign-off. That is a superCPE workflow step, done by a
  human, after ingest.
- Expiration date, sponsor identity, registry ID. Sponsor-level, lives in
  superCPE.

---

# Text packages (`kind: "text"`)

Added by superCPE feature 023. Everything above describes a **video**
package and is unchanged. `manifest.json` gains a `kind` field:

```json
{ "kind": "video" }
```

`kind` is `"video"` or `"text"`. **An absent `kind` means `"video"`**, so
every package exported before this change remains valid and ingests
exactly as before.

A text package is a study guide: the text is the program, review questions
sit between its sections, and any videos are short supplements that add
worked examples or commentary. It is the primary format; video packages
remain supported.

## Layout

    ASC842-GDE-01.zip
      ASC842-GDE-01/
        manifest.json
        guide/
          00-front-matter.md      # role: front_matter
          01-overview.md          # role: body
          02-....md               # role: body  (one file per section)
          90-glossary.md          # role: glossary
          91-appendix-a.md        # role: appendix
        media/
          ex-01.mp4               # optional supplemental videos
        questions.json

There is no `video.mp4` and no `transcript.md`. Every markdown file must
live under `guide/`, every media file under `media/`, and every file in
the zip must be named by the manifest.

## manifest.json (text kind)

```json
{
  "package_version": 1,
  "kind": "text",
  "lesson_id": "ASC842-GDE-01",
  "course_code": "ASC842-GDE",
  "position": 1,
  "title": "Identifying a Lease Under ASC 842",
  "content_hash": "sha256, see definition below",

  "learning_objectives": [
    { "id": "lo-1", "text": "Determine whether a contract contains a lease" }
  ],
  "field_of_study": "Accounting",
  "knowledge_level": "Intermediate",
  "prerequisites": "Basic familiarity with lease accounting",
  "advance_preparation": "None",

  "sections": [
    { "id": "sec-00", "file": "guide/00-front-matter.md",
      "role": "front_matter", "title": "How this course works" },
    { "id": "sec-01", "file": "guide/01-overview.md",
      "role": "body", "title": "Overview" },
    { "id": "sec-90", "file": "guide/90-glossary.md",
      "role": "glossary", "title": "Glossary" },
    { "id": "sec-91", "file": "guide/91-appendix-a.md",
      "role": "appendix", "title": "Appendix A — ASC 842-10 in full" }
  ],

  "media": [
    { "id": "vid-01", "file": "media/ex-01.mp4",
      "placement": { "after_section": "sec-02" },
      "av_is_additional_learning": true,
      "duration_seconds": null }
  ],

  "glossary_terms": [
    { "term": "Right-of-use asset",
      "definition": "An asset that represents a lessee's right to use an
                     underlying asset for the lease term.",
      "section_id": "sec-90" }
  ],

  "sources": [ { "citation": "ASC 842-10-15-3", "role": "primary" } ],
  "author": { "name": "...", "credentials": "CPA",
              "license_jurisdiction": "NH", "license_number": "..." }
}
```

`package_version`, `lesson_id`, `course_code`, `position`, `title`,
`content_hash`, `learning_objectives`, `field_of_study`,
`knowledge_level`, `prerequisites`, `advance_preparation`, `sources`, and
`author` carry exactly the meanings and rules they carry for a video
package. What follows is only what differs.

### Sections and the 7.02.5 word count

`role` is one of `front_matter`, `body`, `glossary`, `appendix`.

**Only `body` sections enter the word count.** This is 7.02.5, which says
the count "should exclude any material not critical to the achievement of
the stated learning objectives," and names the exclusions outright:

> Examples of information material that is not critical and, therefore,
> excluded from the word count are course introduction, instructions to
> the participant, author/course developer biographies, table of contents,
> glossary, pre-program assessment, and appendixes containing
> supplementary reference materials.

and, on reference material:

> If an author/course developer determines, for example, that including
> the entire accounting rule or tax regulation is beneficial to the
> participant, the accounting rule or tax regulation should be included as
> an appendix to the course as supplementary reference material and
> excluded from the word count formula. Only pertinent paragraphs or
> sections of the accounting rule or tax regulation required for the
> achievement of stated learning objectives should be included in the
> actual text of the course and, therefore, included in the word count
> formula.

So: full codification or regulation text goes in an `appendix` section,
excluded; only the pertinent excerpts belong in a `body` section, counted.
The course introduction, the "How this course works" block, author
biographies, and the table of contents belong in `front_matter`. The
glossary belongs in a `glossary` section. Putting excluded material in a
`body` section to raise the count is a fabricated 9.02.2(2)(ii) record.

`word_count` is **not a manifest field for text packages** and is refused
if present. superCPE computes it from the shipped markdown of the `body`
sections at ingestion, and records that the number was computed from
source rather than trusted from a manifest. Video packages keep their
manifest `word_count`, still trusted, still logged as such.

**How superCPE counts.** Per body section, on the shipped markdown:

- fenced code blocks (``` and ~~~) and HTML comments are removed entirely;
- images (`![alt](url)`) are removed entirely;
- links keep their text and lose their URL (`[text](url)` → `text`), and
  link reference definitions (`[ref]: https://…`) are removed;
- HTML tags, heading marks, emphasis marks, blockquote marks, list
  markers, table pipes, and horizontal rules are removed; the words around
  them are kept;
- inline code keeps its content, minus the backticks;
- what remains is split on whitespace, and a token counts as a word if it
  contains at least one letter or digit.

At least one `body` section is required. Every `sections[].file` must
exist in the zip, live under `guide/`, be valid UTF-8, and not be blank.
Section ids are unique within the manifest.

### Front matter and 4.05.3

4.05.3 requires instructional materials to include, at a minimum, an
overview of topics, the ability to find information quickly, the
definition of key terms, navigation instructions, review questions with
feedback, and a qualified assessment. A text package carries three of
those directly:

- **A `front_matter` section is required** and must contain the "How this
  course works" block (4.05.3 item 4, navigation, components, completion).
  The template is at the end of this document; copy it and add anything
  course-specific. superCPE refuses to publish a course whose text lessons
  carry no front matter.
- **`glossary_terms` must not be empty** (4.05.3 item 3). superCPE renders
  them as a course glossary and as an in-reader lookup. Ingestion warns on
  an empty list; the publish gate refuses.
- Keyword search (4.05.3 item 2) is superCPE's, built over the shipped
  section text. Nothing is required of the package.

### Media and 7.02.7

`media` may be empty or absent. Each entry is
`{ id, file, placement: { after_section }, av_is_additional_learning,
duration_seconds }`.

`av_is_additional_learning` **must be `true` on every media item of a text
package.** 7.02.7 lets audio/video duration into the formula only when the
segment "constitute[s] additional learning for the participant (that is,
not narration of the text)." The test is one sentence: **if the video
reads the text aloud, it does not belong in a text package.** There is no
narration branch here — a text package's video minutes always count toward
the A/V term, so the attestation that they genuinely add is part of the
4.02 content review, where the reviewer signs that the supplemental videos
are additional learning and not narration of the guide.

`placement.after_section` must name a section in the same manifest; the
video renders inline at that point in the reader. `duration_seconds` may
be `null`; ffprobe on ingestion is authoritative either way, and a
non-null value that disagrees with the measured duration by more than one
second is rejected, exactly as for video packages.

### glossary_terms

Each entry is `{ term, definition, section_id }`. `term` and `definition`
must be non-blank; terms are unique within the manifest; `section_id`, if
given, must name a section (normally the `glossary` section).

### questions.json

Unchanged except placement: a review question in a text package carries
`"after_section": "sec-NN"` where a video package's carries
`"after_block": 3`. The id must name a section in the same manifest.
Carrying both, or neither, is rejected. Assessment questions are
unchanged and carry no placement.

The reader gates on this: a body section does not unlock until the review
question placed after the preceding section has been answered. That is
5.01.2.1's "placed throughout the program in sufficient intervals," which
is why placing every question after the last section is not acceptable
authoring even though nothing in the format forbids it.

### content_hash

For a text package, the lowercase hex sha256 digest of the concatenation
of the **canonical manifest bytes** (see "The canonical manifest bytes"
under the video kind — the rule is identical), then the raw bytes of:
every `sections[].file` in manifest order, then `questions.json`, then
every `media[].file` in manifest order. Recomputed on ingest and must
match, with the same consequences as for a video package — a re-upload
with the same hash is a no-op, a different hash creates a new lesson
version and marks the course's credit and review stale.

The manifest is inside the hash for a reason this kind makes vivid: a
section whose `role` flips from `appendix` to `body` changes the computed
word count and therefore the credit, while every file in the zip stays
byte-identical.

## The "How this course works" template

Copy into the `front_matter` section. It is excluded from the word count,
so nothing here earns credit; it is here because 4.05.3 item 4 requires
it.

```markdown
## How this course works

This is a self study CPE program. The study guide below is the program;
read it in order.

**Sections.** The guide is divided into sections. Read a section, then
answer the review question that follows it. The next section opens once
the question is answered. You are told immediately whether your answer was
correct, with an explanation either way. Review questions are not scored
toward passing.

**Videos.** Some sections are followed by a short video that works through
an example or adds commentary. The videos add to the guide; they do not
read it aloud. You may scrub or replay them freely.

**Glossary and appendixes.** The glossary and any appendixes are reference
material, available from the course menu at any point. They are not
required reading and do not have to be read in order.

**Finding something.** Use the search box in the course menu to find any
word in the guide, or the glossary lookup for a definition.

**Finishing.** When every review question in the course has been answered,
the qualified assessment opens from the course page. Passing it records
your completion and issues your certificate.
```
