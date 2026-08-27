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
  "title": "Why Percentage of Completion Is No Longer a Method",
  "content_hash": "sha256, see definition below",

  "video": {
    "duration_seconds": 486,
    "duration_source": "measured",
    "measured_at": "2026-08-20T14:02:11Z",
    "narration_blocks": 7,
    "tts_provider": "elevenlabs",
    "tts_voice_id": "HKFOb9iktHA85uKXydRT",
    "tts_model": "eleven_multilingual_v2"
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
- `video.duration_source` must be `"measured"`. video-tool must refuse to export
  while its `usingEstimates` flag is true. superCPE rejects any other value.
  This is how 7.02.7's "actual audio/video duration time" is guaranteed: the
  number is never typed in superCPE, and the tool that produced it attests it
  was measured from the rendered narration.
- `duration_seconds` must match the uploaded mp4 within 1 second, checked with
  ffprobe on the server. A mismatch is rejected, not warned.
- `content_hash` is the lowercase hex sha256 digest of the concatenation of the
  raw bytes of `transcript.md`, then `questions.json`, then `video.mp4`, in
  exactly that order. It is recomputed on ingest and must match. A re-upload
  with the same hash is a no-op; a different hash creates a new lesson version
  and marks the course's credit and review as stale.
- `word_count` is the count of text learning material a participant must
  *read* (7.02.5). For an all-video lesson it is 0 and stays 0. The transcript
  is not reading material and is never counted; it is the transcript of record.
- `field_of_study` must be a value from `docs/2024-Fields-of-Study.pdf`.
- `knowledge_level` must be one of the Standards' defined levels (Basic,
  Intermediate, Advanced, Overview, Update).
- `learning_objectives` is a non-empty array of `{ "id", "text" }` objects.
  Ids must be unique within the manifest; `questions.json` references them
  through `objective_ids`.

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
