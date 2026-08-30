# 013 — Durability of retained records

First Phase B feature. Production is live at `62de030` in `coming_soon`
mode with an empty database. Feature 012's changelog entry is still
owed: it waits on the restore drill and acceptance items 3–5 of 012,
which are the operator's hands, not code. 013 does not depend on them,
but the drill must be run before ASC842-PCX is re-ingested (feature
014), because it is only free while the database is empty.

## Goal

012 put the 9.02 records — completions, certificates, audit bundles,
program materials — in one managed database and one Spaces bucket, both
at DigitalOcean, both protected by application discipline (no delete
paths, write-once keys) and by backups that also live at DigitalOcean.
Two things can still lose a retained record: an accidental overwrite or
delete at the bucket layer, which nothing recovers; and a provider-level
failure (account lockout, region loss, billing lapse), which takes the
originals and every backup together.

After this feature the bucket itself keeps every prior version of a
retained object, a second copy of the database dumps and the small
retained objects lives at a different provider, and `/health` reports
both so the uptime monitor sees them go stale. ROADMAP's "off-provider
backup copies" improvement note is closed by this feature.

## In scope

- Object versioning on `supercpe-prod-nyc3`, enabled once by a script in
  the repo run with a temporary Full Access key, then verified from the
  runtime key on every boot and in `/health`.
- Storage reclamation under versioning: noncurrent versions under
  `backups/` are expired; noncurrent versions under `packages/`,
  `certificates/`, and `audits/` are never expired.
- Off-site copy: `backup.sh` also uploads the nightly dump to a second
  S3-compatible bucket at a different provider, and mirrors
  `certificates/` and `audits/` there. `/health` reports
  `last_offsite_backup_at`.
- Boot validation and `env.production.example` for the new variables.
- COMPLIANCE.md and `docs/OPERATIONS.md` entries; the four runbook
  corrections found during the 2026-08-30 restore-procedure review
  (listed under task 6).

## Out of scope

- CDN, edge caching, or any change to presigned playback (012 decision
  stands).
- Mirroring `packages/` off-site. Videos are large, and every exported
  zip also exists on the machine that produced it (video-tool's
  `dist/`). Recorded as a known gap, not built.
- Encryption at rest beyond what the providers do by default.
- Restoring *from* the off-site copy as an automated path. The
  procedure is documented; the drill for it is a Phase C item.
- Anything touching accounts, enrollments, or course content.

## Locators

Quote these in COMPLIANCE.md rows; do not paraphrase.

- **9.02** — "CPE program sponsors must retain adequate documentation
  (electronic or paper) for a minimum of five years to support their
  compliance with these Standards and the reports that may be required
  of participants." This feature's claim: a record that exists at
  completion still exists five years later even if the bucket is
  mis-handled or the provider is lost. The Standard says *retain*, not
  *back up*; superCPE reads durability as part of retaining.
- **9.02.2(1)** through **9.02.2(7)** — the self-study documentation
  elements the audit bundle already exports (011). The bundle zips under
  `audits/` are the retained form of that set; they are the first thing
  the off-site mirror covers.
- **9.01 item 2** — for self study, the evidence of completion is the
  certificate the sponsor supplies. Certificates under `certificates/`
  are the second thing the mirror covers.

## Human tasks before Claude Code starts

1. Create a bucket at a second provider. Any S3-compatible target works
   (Backblaze B2, Cloudflare R2, Wasabi, AWS S3). Pick a region that is
   not NYC. Private, versioning **on** if the provider offers it.
2. Create a key for that bucket scoped to it alone, read/write/delete.
   Note the endpoint URL, region string, bucket name, key, secret.
3. Create a **temporary** Full Access Spaces key at DigitalOcean for
   task 1 below. It is used once and deleted in the acceptance
   walkthrough. Do not put it in `/srv/supercpe/.env`.

## Tasks

### 1. Bucket setup script

`deploy/bucket-setup.py` — run once, by hand, with Full Access
credentials passed only as environment variables
(`SETUP_SPACES_KEY`, `SETUP_SPACES_SECRET`), never read from `.env`.

- Enables object versioning on the bucket.
- Puts a lifecycle configuration with one rule: expire noncurrent
  versions under prefix `backups/` after `BACKUP_NONCURRENT_DAYS = 7`
  (new constant in `constants/storage.py`, docstring explaining that a
  nightly dump overwritten by the same day's re-run has no retention
  value beyond a week, whereas every other prefix is 9.02 material and
  is never expired). No other rules.
- Prints the resulting versioning status and lifecycle configuration,
  and exits non-zero if either does not read back as set.
- **Verify first** that DigitalOcean Spaces honors
  `NoncurrentVersionExpiration` with a prefix filter. If it does not,
  stop and report before writing the fallback (`backups.py` prune
  would then delete noncurrent `backups/` versions explicitly by
  `VersionId`, and the runtime key needs a permission check for that).
  Do not guess; test it against the real bucket.

Idempotent: running it twice changes nothing and reports the same.

### 2. Versioning as a boot and health check

- `SpacesStorage.versioning_enabled()` — `GetBucketVersioning` with the
  runtime Limited Access key. Confirm the runtime key can read it; if it
  cannot, report before building and we will choose between widening
  the key and dropping the check.
- `ensure_boot_config`: in `prod`, refuse to boot if versioning is not
  `Enabled`. A 9.02 control that can be switched off in a control panel
  and leave the application running normally is a control that will be
  found off during an audit.
- `/health` gains `bucket_versioning: "ok" | "error"`, contributing to
  the 503 rule like the other components. `LocalStorage` reports `ok`
  (there is nothing to version) with a comment saying so.

### 3. Off-site mirror

- Config: `OFFSITE_ENDPOINT`, `OFFSITE_REGION`, `OFFSITE_BUCKET`,
  `OFFSITE_KEY`, `OFFSITE_SECRET`. `ensure_boot_config`: if any is set,
  all must be set; `OFFSITE_SECRET` follows the ≥32-byte rule; in
  `prod`, `OFFSITE_ENDPOINT` must not be the DigitalOcean endpoint
  (that would be a second bucket, not a second provider). Not required
  in `prod` — the missing-offsite state is reported, not refused, so
  the site can stay up while a provider is chosen or replaced.
- `services/offsite.py`: a second boto3 client from the `OFFSITE_*`
  vars. Two operations: `mirror_backup(date)` copies
  `backups/<date>.dump.gz` and stamps `backups/LATEST` in the off-site
  bucket; `mirror_prefix(prefix)` copies every object under
  `certificates/` or `audits/` that is absent off-site or differs by
  ETag. Never deletes anything off-site. Idempotent.
- `backup.sh`: after the local upload succeeds, call a new CLI command
  `mirror-offsite` that runs `mirror_backup` for tonight's date and
  `mirror_prefix` for `certificates/` and `audits/`. A failure here
  logs and exits non-zero **after** the primary backup is already
  stamped, so a dead off-site provider cannot make `last_backup_at`
  stale and mask the primary as the problem.
- On success, write `backups/OFFSITE` in the **primary** bucket
  containing the ISO timestamp. `/health` reads it as
  `last_offsite_backup_at`; `null` when unconfigured or never run.
- `/health` 503 rule: `last_offsite_backup_at` does **not** contribute.
  Staleness is for the uptime monitor to alert on, same as
  `last_backup_at`. Document the ~26-hour threshold for both.

### 4. Retention pruning under versioning

`backups.py` prune currently deletes old dumps. With versioning on, a
delete writes a delete marker; the lifecycle rule from task 1 reclaims
the bytes after `BACKUP_NONCURRENT_DAYS`. Confirm the prune still
behaves (the current-version listing no longer shows pruned dumps) and
add a test with `moto` versioning enabled that asserts pruned dumps are
absent from the current listing and present as noncurrent versions.

### 5. Documentation

- COMPLIANCE.md: append entries (never edit) — 9.02 row for bucket
  versioning replacing the "no object versioning" gap that 012's entry
  already corrected once; 9.02 row for the off-site copy; 9.02.2 and
  9.01 rows noting which prefixes are mirrored and that `packages/` is
  not, with the reason.
- `docs/OPERATIONS.md`: new section "Off-site copy" (provider, bucket,
  where its key came from, how to restore a dump from it — same
  `pg_restore` path with a different download step); "Bucket
  versioning" section (how to recover a prior version of an object by
  `VersionId`, and that the runtime key cannot change versioning or
  lifecycle); add the off-site provider login to "Who and where".
- `deploy/env.production.example`: the five `OFFSITE_*` lines, marked
  optional, with the different-provider rule stated.
- ROADMAP.md: remove nothing; append a line under the improvement notes
  saying the off-provider note is closed by 013, and add the
  `packages/` off-site gap as a new note.

### 6. Runbook corrections from the 2026-08-30 review

These are small and belong in this commit, not a separate one.

- Restore, dump path, step 3: the `postgres:16 pg_restore` container
  reaches the VPC private host because container traffic NATs through
  the droplet, which is the cluster's trusted source. One sentence, so
  nobody adds a Cloud Firewall rule that breaks it.
- Restore, dump path: the scratch database has the same ownership trap
  as the first-deploy step 6 — a panel-created database is owned by
  `doadmin`. Say to either restore as `doadmin` or `ALTER DATABASE ...
  OWNER TO supercpe` first.
- Restore, dump path, step 2: the api container runs as non-root and
  writes into a host mount. If it fails with `PermissionError`, the fix
  is `--user $(id -u)` on the `docker compose run`. Add the flag to the
  documented command.
- Restore drill record: the empty-row text says "against the empty
  production database"; production is never the target. Reword to "from
  the most recent dump into a scratch database". Add a fourth
  verification that is not vacuous on an empty database:
  `alembic_version` matches production, table list matches, account
  count matches.
- "Who and where": the DigitalOcean owner line still carries a
  "confirm/correct" note. Leave the note; the operator will resolve it.

## Acceptance

Claude Code runs 1–4 and 8. The operator runs 5–7 on production after
deploy and reports results.

1. `pytest` all pass, count > 227. New tests cover: boot refusal when
   versioning is not enabled in `prod`; `OFFSITE_*` all-or-nothing;
   same-provider endpoint refused in `prod`; `mirror_prefix` copies
   missing and changed objects and never deletes; `mirror_backup`
   stamps `LATEST` off-site and `OFFSITE` in the primary; `/health`
   shows `bucket_versioning` and `last_offsite_backup_at`; prune under
   versioning per task 4.
2. `bucket-setup.py` against a `moto` bucket: enables versioning, sets
   exactly one lifecycle rule, is idempotent, exits non-zero if
   read-back fails.
3. `ensure_boot_config` with `OFFSITE_*` unset in `prod` boots and
   `/health` reports `last_offsite_backup_at: null`.
4. `backup.sh` with off-site failing: primary `LATEST` is stamped, exit
   code is non-zero, log names the off-site step as the failure.
5. **Operator:** run `bucket-setup.py` with the temporary key, see
   versioning `Enabled` and the one rule; delete the temporary key;
   confirm `/health` shows `bucket_versioning: ok` after deploy.
6. **Operator:** run `backup.sh` by hand; the dump, `LATEST`, and the
   (empty, today) `certificates/` and `audits/` prefixes appear at the
   second provider; `/health` shows `last_offsite_backup_at` within a
   minute of now.
7. **Operator:** overwrite `health/sentinel` by running `write-sentinel`
   twice, then list versions of that key and see two. Recover the older
   by `VersionId` per the new OPERATIONS.md section. (This is the
   recovery drill for the bucket layer; record its date next to the
   restore drill.)
8. Secrets nowhere in the repo: `git grep -i offsite_secret` and
   `git grep -i setup_spaces` return only the example file and the
   script's variable names.

## When done

Write the 013 changelog entry per CLAUDE.md. Cover: why boot refuses on
versioning-off but only reports on offsite-missing; why `packages/` is
not mirrored; the lifecycle rule and why `backups/` alone; what
DigitalOcean actually honored in the lifecycle API; the provider
chosen off-site and why; and the 012 runbook corrections folded in.

Then stop. 014 is the ASC842-PCX re-ingest on production with the real
second CPA's review, and it is gated on the 012 restore drill being
dated in `docs/OPERATIONS.md`.
