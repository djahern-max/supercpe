# Current Feature

## Feature 002, Course package ingest

## Goal
superCPE can receive a lesson package from video-tool, validate every rule in
`docs/course-package.md`, and retain it verbatim. After this feature the
platform has its first real data, and the boundary between the two repos is
enforced by code rather than by a document.

Ingest validates and retains. It does not interpret. Questions, objectives,
credit, and review are later features that read what this one stores.

## In scope
- A `lesson_packages` table holding the validated scalars plus the raw manifest,
  questions, and transcript verbatim
- `POST /api/v1/admin/packages` accepting a zip, running every contract rule,
  returning every failure at once
- Duration verification with ffprobe, hash verification, idempotent re-upload,
  versioning on content change
- A storage abstraction with a local-disk implementation
- A minimal admin token so the route is not open
- An admin page to upload a package and see ingested lessons
- Fields-of-study and knowledge-level constants transcribed from the PDFs
- First rows in `COMPLIANCE.md`

## Out of scope
- DigitalOcean Spaces. Storage is local disk behind an interface; Spaces is a
  second implementation of that interface at deployment time.
- Courses. A lesson package is not yet attached to anything. Feature 004.
- Normalizing questions or objectives into their own tables. Features 004, 006,
  007 do that by reading the JSON this feature stores.
- Real authentication. A shared token is enough to keep a local route closed.
  Accounts and roles are feature 009.
- Any participant-facing surface.

## Contract edit, do first
`docs/course-package.md` has an inconsistency: `questions.json` references
objectives by `objective_ids`, but the manifest's `learning_objectives` is a
bare string array with no ids. Change the manifest field to:

```json
"learning_objectives": [
  { "id": "lo-1", "text": "Distinguish a method from an output measure under ASC 606" }
]
```

Ids must be unique within the manifest. Nothing has produced a v1 package yet,
so this stays `package_version: 1`. Note the edit in the changelog.

## Locators this feature is built against
Read these in `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf` before
writing code, and take COMPLIANCE.md's Requirement column from the PDF's words.

- 3.01.1 — knowledge levels are Basic, Intermediate, Advanced, Update, Overview
- 3.02.1 — Intermediate, Advanced, Update must state prerequisites and advance
  preparation; Basic and Overview state "none" if not applicable
- 7.02.7 — "actual audio/video duration time (not narration of the text)"
- 9.02.1(8) and 9.02.2 — program materials retained
- `docs/2024-Fields-of-Study.pdf` — the field-of-study list

For 7.02.7 the COMPLIANCE row should say plainly what this feature does and
does not guarantee: the duration is measured by ffprobe on the server against
the file that was uploaded, and video-tool attests the narration was rendered
from measured audio. superCPE cannot verify the second claim; it can only
refuse packages that do not make it.

## Data model
Table `lesson_packages`:
- id: integer PK
- lesson_id: string, not null, indexed. The external id from the manifest.
- version: integer, not null. Starts at 1 per lesson_id, increments when a
  package with the same lesson_id and a different content_hash is ingested.
- content_hash: string, not null, unique
- title: string, not null
- duration_seconds: integer, not null
- duration_source: string, not null, CHECK = 'measured'. The constraint exists
  so the column can never hold anything else even if the validator is bypassed.
- measured_at: timezone-aware timestamp, not null
- narration_blocks: integer, not null
- word_count: integer, not null
- av_is_additional_learning: boolean, not null
- field_of_study: string, not null, CHECK against the constant
- knowledge_level: string, not null, CHECK against the five values
- prerequisites: text, not null
- advance_preparation: text, not null
- manifest: JSONB, not null. The full manifest, verbatim.
- questions: JSONB, not null. The full questions.json, verbatim.
- transcript: text, not null
- video_key: string, not null. Storage key, not a URL.
- ingested_at: timezone-aware timestamp, server default

Unique constraint on (lesson_id, version).

Store the raw JSON alongside the scalars deliberately. The scalars are what this
feature validated; the JSON is what later features will normalize. Keeping both
means a later feature that discovers ingest missed a rule can re-validate
history without asking for re-uploads.

## Validation rules
Every rule below produces a message naming the field and the rule. The response
collects all failures and returns them together as 422 `{"errors": [...]}`.
Nothing is written to storage or the database unless every rule passes.

Zip structure:
1. Exactly one top-level directory, containing exactly `manifest.json`,
   `video.mp4`, `transcript.md`, `questions.json`. Extra or missing files fail.

Manifest:
2. `package_version == 1`; message names the version received.
3. Required fields present with correct types: everything shown in the contract.
4. `video.duration_source == "measured"`. Message states that estimated
   durations are refused under 7.02.7 and that video-tool must export with
   measured audio.
5. `video.duration_seconds` within 1 second of ffprobe's reading of the
   uploaded mp4. Message shows both numbers.
6. `content_hash` equals sha256 over transcript.md bytes + questions.json bytes
   + video.mp4 bytes, in that order, concatenated. Document this exact
   definition in `docs/course-package.md` too; the contract currently says it
   loosely.
7. `word_count >= 0`.
8. `field_of_study` in `FIELDS_OF_STUDY`.
9. `knowledge_level` in `KNOWLEDGE_LEVELS`.
10. If `knowledge_level` in intermediate/advanced/update: `prerequisites` and
    `advance_preparation` non-blank. If basic/overview: blank is permitted and
    is stored as the literal string "None" (3.02.1 wants "none" stated, not
    omitted).
11. `learning_objectives` non-empty, each with unique `id` and non-blank `text`.
12. `sources` non-empty. A lesson with no cited authority is not a CPE lesson.

Questions:
13. Non-empty array. Each has `id` (unique), `kind` in {review, assessment},
    `stem`, `choices`, `correct`, `feedback`, `objective_ids`.
14. `correct` is the id of one of `choices`.
15. Review questions: at least 2 choices and an `after_block` in
    `[1, narration_blocks]`. Assessment questions: at least 3 choices, no
    `after_block`.
16. Every `objective_ids` entry exists in the manifest's objectives. Every
    question has at least one.
17. `feedback` non-blank.

Do not validate stem or feedback quality. That is the content reviewer's job in
feature 008.

Idempotency and versioning, after validation:
- Same `content_hash` already stored: return 200 with the existing record and
  `"created": false`. Write nothing.
- Same `lesson_id`, new hash: create version N+1. Return 201.
- New `lesson_id`: version 1. Return 201.

## Backend tasks
1. `app/constants/fields_of_study.py`: `FIELDS_OF_STUDY`, transcribed from
   `docs/2024-Fields-of-Study.pdf`. Each entry carries the name and whether
   NASBA classifies it technical or non-technical; nothing reads the flag yet,
   but transcribing the list twice is worse than carrying it once. Cite the PDF
   in the module docstring.
   `app/constants/knowledge_levels.py`: the five levels and the subset that
   requires prerequisites, citing 3.01.1 and 3.02.1.
2. `app/models/lesson_package.py`, then
   `alembic revision --autogenerate -m "create lesson_packages"`. Add the CHECK
   constraints by hand. Verify `downgrade -1`.
3. `app/storage.py`: a `Storage` protocol with `put(key, fileobj) -> None`,
   `open(key) -> BinaryIO`, `exists(key) -> bool`. `LocalStorage` rooted at
   `settings.STORAGE_ROOT` (default `backend/uploads/`, already gitignored).
   Keys are `packages/<lesson_id>/v<version>/video.mp4`. A `get_storage()`
   dependency returns the configured implementation; there is one.
4. `app/services/ffprobe.py`: `duration_seconds(path) -> Decimal` via
   `subprocess.run(["ffprobe", ...])`, JSON output, no wrapper library. Raise a
   clear error if ffprobe is not on PATH, and check for it at app startup so the
   failure is at boot, not at first upload.
5. `app/services/packages.py`:
   - `validate(zip_path) -> ValidatedPackage | list[str]` running rules 1–17 in
     order, collecting all messages. Pure; no DB, no storage.
   - `ingest(db, storage, validated) -> tuple[LessonPackage, bool]` handling
     idempotency and versioning. Storage write happens inside the same
     transaction scope as the DB write; if storage fails, nothing commits.
   - `list_packages(db)` newest first, and `get_package(db, id)`.
6. `app/auth.py`: `require_admin` dependency reading `X-Admin-Token`, comparing
   with `secrets.compare_digest` against `settings.ADMIN_TOKEN`. 401 on missing
   or wrong. Add `ADMIN_TOKEN` to config and both `.env.example` files.
7. `app/routers/admin_packages.py` under `/api/v1/admin`, router-level
   `require_admin`:
   - `POST /packages` multipart zip upload. Save to a temp dir, validate,
     ingest, clean up the temp dir in a `finally`.
   - `GET /packages` list. `GET /packages/{id}` detail including the raw
     manifest and questions. Neither returns the transcript by default; add
     `GET /packages/{id}/transcript` returning text/markdown.
   Register in `main.py`.
8. `app/schemas/package.py`: summary and detail schemas; `IngestResponse` with
   `package` and `created`.
9. Test fixture `tests/factories/package.py`: `build_package(tmp_path, **over)`
   writes a valid package to disk. Generate the mp4 with
   `ffmpeg -f lavfi -i color=c=black:s=64x64:d=2 -f lavfi -i anullsrc -t 2`
   so the fixture is tiny and real. Computes the hash correctly by default;
   overrides let tests break individual fields.
10. `tests/test_packages.py`:
    - valid package ingests, 201, video exists in storage at the expected key
    - missing token 401; wrong token 401
    - `duration_source: "estimated"` refused and message mentions 7.02.7
    - `duration_seconds` off by 2 refused, message shows both numbers
    - tampered transcript (hash mismatch) refused
    - three broken fields at once returns three messages in one response
    - re-upload of identical package returns 200, `created: false`, one row
    - changed transcript with same lesson_id creates version 2
    - intermediate level with blank prerequisites refused; basic level with
      blank prerequisites stores "None"
    - assessment question with 2 choices refused
    - question referencing unknown objective id refused
    - review question with `after_block` beyond `narration_blocks` refused
    - unknown field of study refused
    - a validation failure writes nothing to storage or the database

## Frontend tasks
1. `npm install react-router-dom`. Wrap App in `BrowserRouter`; routes `/`,
   `/admin/packages`, `*`.
2. `src/api/client.js`: support a multipart POST and an optional headers arg.
   `src/api/admin.js`: `uploadPackage(file, token)`, `listPackages(token)`,
   `getPackage(id, token)`.
3. Token handling: a small `src/admin/token.js` that keeps the token in memory
   for the session and a one-field form on `/admin/packages` when it is unset.
   Do not use localStorage.
4. `src/pages/AdminPackages/`: file input accepting `.zip`, upload button,
   result panel. On 422 render every error as its own line; on 201 show the
   lesson id, version, title, and duration; on 200-not-created say so plainly.
   Below, a table of ingested packages: lesson id, version, title, duration
   formatted as m:ss, field of study, level, ingested at. Click a row for a
   detail view showing the manifest and questions as formatted JSON and a
   link to the transcript.
5. CSS Modules using the global tokens. Loading, error, and empty states
   handled explicitly.

## COMPLIANCE.md
Add rows for 3.01.1, 3.02.1, 7.02.7, and 9.02.1(8). The 7.02.7 Gap column
must state that superCPE verifies the file's duration but cannot verify that
the narration inside it was rendered from measured audio; it relies on
video-tool's attestation and refuses packages that lack it.

## Acceptance criteria
- App refuses to start with a clear message if ffprobe is missing
- All tests in `test_packages.py` pass; `pytest` passes overall
- `alembic downgrade -1` then `upgrade head` round-trips
- Using a hand-built package from the test factory (add a
  `scripts/make_sample_package.py` that writes one to `/tmp`), the admin page
  ingests it, lists it, and a second upload reports not created
- Editing `duration_source` to `estimated` in that zip and re-uploading shows
  the 7.02.7 message in the UI
- `backend/uploads/` is untracked after all of this
- COMPLIANCE.md has four rows with Requirement text taken from the PDF

## When done
Append the 002 entry to `CHANGELOG.md`. Under Decisions record the storage
interface choice and the raw-JSON-plus-scalars choice. Under Known gaps
record: shared-token auth is temporary; Spaces not yet implemented; the
video-tool attestation is trusted, not verified. Then stop.
