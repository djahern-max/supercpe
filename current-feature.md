# Feature 038 — Package version lifecycle: archive, delete, purge media

## Goal

Lessons get re-exported as they improve (GPT-06 was the first real case,
2026-09-15). Every re-upload creates a new package version, and the old
versions pile up on the admin packages page forever. Today the only way to
remove one is Delete, and it fails badly: deleting a version that any
enrollment touched fails in Postgres (`lesson_progress_package_id_fkey`,
then `attempt_answers` / `review_answers` through `questions`). The page
gets a 500 and shows "Delete failed. Try again."

Give each package version a lifecycle the admin can see and act on:

- **Unused** (no enrollment ever pinned it, not attached): delete outright,
  as today, but with a readable refusal when it isn't unused.
- **Used, within retention**: **archive**. It leaves the packages list and
  can't be attached, but every row and stored file stays.
- **Used, past retention**: **purge media**. The stored video and media
  files are deleted from storage. The database rows (manifest, transcript,
  sections, questions, choices) and every participant record stay.

Nothing in this feature deletes an enrollment, attempt, answer, progress
row, completion, or certificate. Purging media is the only new destructive
act, and only after the retention date has passed.

## Standards touched

Read each paragraph in `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`
before writing code and name the printed page in the changelog (the
2026-09-13 brand-assets decision read 9.02 / 9.02.2 on printed page 22;
confirm it, don't copy it).

- **9.02**: sponsors keep documentation for a minimum of five years.
  This feature starts acting on the far side of that minimum for one
  element only.
- **9.02.2(7) / 9.02.1(8)**: program materials. The stored video/media
  files are what purge removes, and only once every participant record
  that references the version is past `RETENTION_YEARS`.
- **9.02.2(1)**: completion records. Untouched: rows are never deleted,
  and the manifest, transcript, and questions stay so the record can still
  show what was asked.

## Reversals (CLAUDE.md rule 7)

This spec asks for the following, and the changelog must name each as a
reversal of the specific earlier decision:

1. `backend/app/constants/retention.py` and
   `backend/app/services/retention.py` docstrings: "nothing enforces
   deletion after it … superCPE keeps everything." Reversed **for package
   media files only**: past the date, an admin may purge them.
2. COMPLIANCE.md 9.02 rows from 002 and 010 ("Nothing is ever deleted",
   packages FK RESTRICT). Add a new row saying what changed; never edit the
   old rows (append-only, like the 2026-08-30 corrections).

Not reversed: "Participants keep the package versions they enrolled on"
holds for the whole retention period; accounts, enrollments, attempts,
answers, progress, completions, and certificates are still never deleted.

Write `docs/decisions/2026-09-15-package-version-lifecycle.md` recording
the three states, the retention anchor below, and why purge removes files
but keeps rows.

## Definitions (derived, never stored as booleans)

For a package version P:

- **referencing enrollments**: enrollments whose `package_versions` pins
  P, plus any enrollment with an attempt whose `package_versions` lists P,
  or with `lesson_progress` / `review_answers` on P. Findings confirm the
  complete list, including whether admin preview writes any of these.
- **used**: at least one referencing enrollment exists.
- **attached**: a `course_lessons` row points at P.
- **archived**: `archived_at IS NOT NULL`.
- **retain_until(P)**: the latest, across referencing enrollments, of
  `retain_until(anchor)`, where anchor is the completion's `completed_at`
  if the enrollment completed, else the enrollment's `expires_at`.
  `null` when P is unused.
- **deletable**: not used and not attached.
- **media purgeable**: used, archived, not attached, `retain_until(P)` is
  in the past, and media not already purged.

`RETENTION_YEARS` and `retain_until()` are reused, not duplicated.

## In scope

1. **Findings first.** Before changing anything, report:
   - Every table and JSONB column that references a package version
     (FKs and non-FK pins), and which of them block `DELETE FROM
     lesson_packages` today.
   - Whether admin preview of a lesson writes progress or answers.
   - What storage objects a package owns (`video_key`, `package_media`,
     anything else under `packages/`) and whether `storage.delete` covers
     all of them.
   - With bucket versioning on (013), what `storage.delete` actually does
     under `packages/`: a delete marker, with the bytes kept as a
     noncurrent version that the lifecycle rule never expires. State
     plainly whether purge reclaims storage or only removes the current
     object.
   - Whether the runtime Limited Access key can delete under `packages/`.
   - What the audit bundle references by storage key, and what it does
     when that key no longer exists.
   - Whether an admin action log exists that purge should write to.
2. **Delete refuses readably.** `delete_package` checks used and attached
   before deleting and returns 422 `{"errors": [...]}` naming why (for
   example, "GPT-06 v1 is referenced by 1 enrollment; archive it
   instead"). The endpoint never 500s on a referenced version; a test
   proves the FK path is unreachable.
3. **Archive / unarchive.** `archived_at` (timestamp) on
   `lesson_packages`, with a migration. `POST
   /api/v1/admin/packages/{id}/archive` refuses while attached;
   `/unarchive` clears it. Attaching or `update-version` to an archived
   package is refused with 422. Re-uploading a zip whose hash matches an
   archived version stays a no-op and reports that the version is archived.
4. **Purge media.** `POST /api/v1/admin/packages/{id}/purge-media` refuses
   unless media purgeable (422 with the reason and the date). On success
   it deletes every storage object the package owns and records
   `media_purged_at` and `media_purged_by` (account email snapshot, like
   `recorded_by` on reviews). A CHECK constraint ties the two together.
   Rows are not deleted. Purge is idempotent-refused: a second call is 422.
5. **After purge, degrade, don't break.** Any participant, admin, or
   audit-bundle path that would fetch a purged object says "materials for
   this version were removed on {date} after the retention period" instead
   of erroring. Transcript, questions, and credit breakdown still render.
6. **List payload.** `GET /api/v1/admin/packages` excludes archived by
   default; `?include_archived=true` includes them. Each summary gains
   `archived_at`, `enrollment_count`, `attached_course_codes`,
   `retain_until`, `deletable`, `media_purgeable`, `media_purged_at`.
7. **Admin packages page.** A "Show archived" toggle. Per row: Delete
   (enabled only when deletable), Archive / Unarchive, and Purge media
   (shown only when archived; enabled only when purgeable, otherwise shows
   "Media can be purged after {retain_until}"). Purge confirms with the
   lesson id, version, and the sentence "The video and media files are
   deleted. Participant records and questions are kept." The existing
   generic "Delete failed" message stays only for genuinely unexpected
   errors; 422 reasons render as errors.

## Out of scope

- Deleting any participant record, or any package row that is used.
- Automatic or scheduled purging. Purge is always one admin clicking one
  version.
- Changing the bucket lifecycle rule to expire noncurrent `packages/`
  versions. If findings show purge leaves the bytes as noncurrent versions,
  record it under Known gaps and in ROADMAP improvement notes; do not
  change bucket configuration.
- Any change to the course package contract, video-tool, credit math,
  gating, or certificates.
- Cleaning up package 6 (GPT-06 v1) in production. It's test data; the
  operator handles it.

## Data model

`lesson_packages`: `archived_at timestamptz null`, `media_purged_at
timestamptz null`, `media_purged_by text null`. CHECK: `media_purged_at`
and `media_purged_by` are both null or both set; CHECK: `media_purged_at`
requires `archived_at`. Hand-written in the Alembic migration
(autogenerate won't write CHECKs). No new tables.

## Tests

Backend:
- Delete of an unused, unattached version succeeds and removes its storage
  objects (stubbed storage).
- Delete of an attached version, and of a version pinned by an enrollment
  with no progress, and of one with progress/answers/attempts: each 422
  with a reason, never 500, rows unchanged.
- Archive refuses while attached; archived versions are excluded from the
  list by default and included with the flag; attach and update-version to
  an archived version 422.
- `retain_until(P)`: completed enrollment anchors on `completed_at`;
  incomplete anchors on `expires_at`; with several enrollments the latest
  wins; Feb 29 behaves as `retain_until()` already does.
- Purge refuses when not archived, when attached, when unused (delete
  instead), and one day before `retain_until`; succeeds one day after
  (frozen clock); deletes every owned object; sets both columns; leaves
  every enrollment, attempt, answer, progress, completion, question, and
  section row intact; a second purge 422s.
- After purge: the reader/player, admin package view, and audit bundle
  return the "materials removed" state, not an error.
- Constraint tests for both CHECKs.

Frontend:
- Show archived toggle changes the request.
- Button enablement follows `deletable` / `media_purgeable` from a mocked
  payload, with the "after {date}" text.
- A 422 on delete renders the server's reasons, not "Delete failed".
- Purge confirm text names the lesson and version.

## COMPLIANCE.md rows

- 9.02 / 9.02.2(7): new row citing 038. Package media may be purged by an
  admin only after every referencing participant record is past
  `RETENTION_YEARS`; package rows and all participant records are retained
  regardless; name the reversal of the 002/010 "nothing is ever deleted"
  rows for media files. Gap: whatever findings say about noncurrent
  versions in the bucket.

## Acceptance

1. Findings report delivered, including the bucket-versioning answer.
2. All tests pass; pyflakes, oxlint, both suites, and `sync_brand.py
   --check` are green; `git status --porcelain` shows only this feature.
3. Locally: upload v1 and v2 of a lesson, enroll a test participant on v1,
   detach v1. Delete is refused with a readable reason; Archive works; Purge
   is disabled with the date. With the clock moved past `retain_until`,
   Purge removes the files and the participant's completion and certificate
   still render.
4. Operator-only (list under Known gaps if not run): deploy, then archive
   GPT-06 v1 on supercpe.com.

## When done

Append CHANGELOG entry 038 in the existing format. Name both reversals under
Decisions. Put the bucket noncurrent-version finding under Known gaps.
