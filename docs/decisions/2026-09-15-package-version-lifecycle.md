# Decision — Package versions are deleted, archived, or have their media purged

Recorded: 2026-09-15 (feature 038)
Status: decided
Reverses: for package media files only, 011's "Nothing deletes at the
boundary: retention is a floor and superCPE keeps everything"
(`backend/app/constants/retention.py`, `backend/app/services/retention.py`)
and the "Nothing is ever deleted" claim in the 002 and 010 COMPLIANCE.md
9.02 rows. Does not reverse "Participants keep the package versions they
enrolled on", or deactivate-never-delete for accounts, enrollments,
attempts, answers, progress, completions, and certificates.

## The decision

A lesson re-exported from video-tool is a new package version. A version
that is no longer attached to any course is in one of three positions,
derived on every read from the records that reference it
(`backend/app/services/package_lifecycle.py`), never stored as flags:

1. **Unused.** No enrollment pins it, no progress, review answer, or
   attempt answer points at it, no attempt lists it, including preview
   attempts. It can be **deleted**: rows and stored files. This was already
   possible. What changes is that a refusal now names its reason as a 422
   instead of failing on a foreign key as a 500.
2. **Used, within retention.** It can be **archived**: `archived_at` is
   set, it leaves the admin packages list by default, and attach and
   update-version refuse it. Every row and every file stays. Unarchive
   reverses it.
3. **Used, past retention.** Once archived, and once the retention date of
   every record referencing it has passed, an admin can **purge its
   media**: the stored video (video kind) or supplemental media files (text
   kind) are deleted from storage, and `media_purged_at` / `media_purged_by`
   record when and by whom. The rows (manifest, transcript, sections,
   questions, choices) and every participant record stay. A purged version
   cannot be unarchived.

Nothing is automatic. Purge is one admin acting on one version.

## The retention anchor

A version's `retain_until` is the latest `retain_until(anchor)` across the
records that reference it:

- an enrollment that completed: its completion's `completed_at`, the
  9.02.2(1) record's own date;
- an enrollment that did not complete (active, expired, or voided): its
  `expires_at`, which is the latest moment anything could have been
  recorded on it (the assessment refuses after it), and later than any
  void;
- a preview attempt (007): its `submitted_at`, else `started_at`.

So 9.02's five years run from the last record on the version, not from
the upload. A version superseded in 2027 whose last participant finished
in March 2028 keeps its files until March 2033.

## Why files and not rows

The operator's goal was to stop keeping stale videos forever, not to erase
what a participant did. Deleting a used package's rows would cascade into
questions and choices, which `attempt_answers` and `review_answers` hold
without ON DELETE on purpose (010), so the only way to delete the rows is
to delete the 9.02.2(1) evidence of how a certificate was earned. Purging
the files and keeping the rows means the completion record can still show
what was asked and answered, the 9.02.2(2)(ii) calculation still rebuilds
from stored durations and counts, and the transcript of record stays.
Only the heavy objects go, and only once their retention floor is behind
them.

## Why preview attempts count

A preview sitting's answers reference the version's questions exactly as a
participant's do. The database refuses the delete either way, and the
preview attempt is a retained sitting (007). Counting it keeps the refusal
readable and gives it a retention anchor. The cost is that a version
someone previewed the assessment on can be archived but not deleted.

## What the Standards say (read for 038)

2026 Statement, `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`:

- 9.02 (printed page 22): "CPE program sponsors must retain adequate
  documentation (electronic or paper) for a minimum of five years to
  support their compliance with these Standards and the reports that may
  be required of participants." A minimum. Beyond it, retention is the
  sponsor's choice.
- 9.02.2 (printed pages 23–24), for self study: (1) "Records of program
  completion verification by individual participant, including the number
  of CPE credits earned by participant and course completion date" (kept,
  untouched); (2)(ii) the word count formula calculation and its data
  (kept, since it lives in `courses.credit_breakdown` and the package rows);
  (7) "Program materials", the one element whose files purge removes, and
  only past the minimum.

## What a purge does not reclaim

The bucket has object versioning on (013) and the lifecycle rule expires
noncurrent versions only under `backups/`. A purge's `DeleteObject` writes
a delete marker, and the bytes stay as a noncurrent version under
`packages/`, recoverable by the Bucket versioning runbook. A purge
therefore removes the file from every superCPE surface but frees no
storage. Reclaiming it would need its own decision. It is recorded as a
ROADMAP improvement note and not built.
