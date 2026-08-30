# 014 — Production catches up, and ASC842-PCX becomes real

Phase A closed 2026-08-30. Production is live at `62de030` in
`coming_soon` mode; 013 (durability) is built and its changelog entry
landed, but its code is **not deployed** — the `prod` boot refusal means
nothing at or after 013 can run until object versioning is enabled on
the bucket. The operator decided on 2026-08-30 that the off-site mirror
stays dormant (no second-provider bucket for now); that decision is
recorded in COMPLIANCE.md and ROADMAP and is not revisited here.

This feature has almost no code. It is the operator's walkthrough that
makes production current and puts the first real course on it, with the
real second CPA's review — the thing the 012 deploy deliberately left
out when production started empty. Claude Code's part is verification
and the records.

## Goal

Production runs current `main` with `bucket_versioning: ok`, the
bucket-layer recovery drill is dated next to the restore drill, and
ASC842-PCX is published on production with a first-person review by a
real, licensed second CPA — so the NASBA application packet (audit
bundle, credit record, review record, certificate sample) can be
generated from real data, not fixtures.

## In scope

- Running `deploy/bucket-setup.py` against the real bucket with a
  temporary Full Access key; recording exactly what DigitalOcean's
  lifecycle API honored (this closes the open verification in 013's
  changelog entry); deleting the key.
- Deploying current `main`; `/health` green including
  `bucket_versioning: ok` and `last_offsite_backup_at: null`.
- The bucket-layer recovery drill (013 acceptance 7), dated in
  `docs/OPERATIONS.md`.
- Re-ingesting ASC842-PCX from video-tool's four exported zips,
  assembling and publishing the course.
- The real second CPA: SME record, reviewer account, first-person
  review.
- The closeout records: 014 changelog entry, a COMPLIANCE.md correction
  row once versioning is verified against the real bucket, drill dates
  in OPERATIONS.md.

## Out of scope

- The sponsor profile / legal entity. It stays blank; certificate
  issuance stays correctly blocked, which matters to no one until
  participants exist.
- Enrollments, testers, participants of any kind.
- The coming-soon landing page and waiting list (015).
- The off-site provider (dormant by the 2026-08-30 decision).
- Deleting the 012 acceptance sample. The ASC606-CON draft course
  cannot be deleted — `audit_exports.course_id` is FK RESTRICT and its
  export log row correctly pins it — and that is retention working, not
  a bug. It stays in draft, invisible to anyone but staff, and
  `packages/ASC606-CON-01/v1/video.mp4` stays where it is.
- The Phase B ops backlog (password rotation, OS updates) — still owed,
  still not part of any feature.

## Locators — read before the review steps

- **4.02** — the review must be by a qualified person other than the
  developer, before first presentation; here that is the real second
  CPA, recorded in the first person from their own reviewer account.
- **4.01.1** — the developer of record on the course.
- **9.02.2(4)** — the reviewer's name, credentials, and license details
  are retained with the record; the SME row is that record.
- **9.02** / **9.02.2(7)** — versioning becomes a live control on the
  bucket that now holds real program materials.

## Operator walkthrough (production)

Do these in order; paste outputs back for the records.

1. **Bucket setup.** Per `docs/OPERATIONS.md` § Bucket versioning:
   create a temporary Full Access Spaces key, run
   `deploy/bucket-setup.py` with `SETUP_SPACES_KEY`/`SETUP_SPACES_SECRET`
   as environment variables, keep the printed read-back (versioning
   status and the lifecycle configuration exactly as DigitalOcean
   returned it), then **delete the key** in the control panel. If the
   script exits non-zero because DigitalOcean did not honor the
   prefix-filtered `NoncurrentVersionExpiration`, stop and report —
   the fallback is a code change (013 task 1 documented it), not a
   retry.
2. **Deploy `main`** with `deploy.sh` (remember the `GIT_SHA` export
   rule for any manual compose commands). Verify `/health`: every
   component ok, `bucket_versioning: ok`, `last_offsite_backup_at:
   null`, sha = the deployed commit.
3. **Recovery drill** (013 acceptance 7): run `write-sentinel` twice,
   list versions of `health/sentinel`, recover the older by `VersionId`
   per the runbook, and date the drill in `docs/OPERATIONS.md` next to
   the restore drill.
4. **Re-ingest** per `docs/OPERATIONS.md` § Re-ingest a course: upload
   `ASC842-PCX-01.zip` … `-04.zip`, create the draft course, attach in
   manifest order, confirm the credit panel is fresh and readiness
   shows only the developer/review blocks.
5. **The real review.** Create the SME records: the developer of record
   and the second CPA (name, credentials, license jurisdiction/number,
   active status — recorded as stated). Create the second CPA a
   reviewer account; they sign in themselves, change the initial
   password, and record the approval in the first person at `/review`.
   The developer and reviewer must be different people; readiness
   enforces it.
6. **Publish.** Publish succeeds with no block findings; a logged-out
   visit to https://supercpe.com still shows only the coming-soon
   placeholder; signed-in staff see the published course with its
   provenance line.

## Claude Code tasks

1. Verify what is verifiable from here: `/health` after deploy (public
   endpoint), and that the repo needed no code for any of the above. If
   a bug surfaces during the walkthrough, fix it as its own changelog
   entry, not inside 014's.
2. When the operator reports 1–6: write the 014 changelog entry
   recording the DigitalOcean lifecycle read-back verbatim-in-substance
   (closing 013's "moto only" gap), the drill date, the deployed sha,
   and the course/review provenance. Append the COMPLIANCE.md
   correction row: the 9.02 versioning control is now verified against
   the real bucket. Update the 013-pending memory.

## Acceptance

1. `bucket-setup.py` read-back shows versioning `Enabled` and exactly
   one lifecycle rule; the temporary key no longer exists.
2. `/health` on production: all components ok, `bucket_versioning: ok`,
   `last_offsite_backup_at: null`, version = current `main`.
3. The bucket-layer recovery drill is dated in `docs/OPERATIONS.md`.
4. Four ASC842-PCX packages ingested at v1; objects present under
   `packages/ASC842-PCX-0N/v1/`.
5. The course is published; readiness had no block findings; the
   review on record was recorded by the reviewer's own account
   (`recorded_by` is the second CPA's email, role reviewer), and the
   reviewer is not the developer.
6. Logged out, supercpe.com shows only the coming-soon placeholder.
7. `pytest` still passes with no count change expected; any code change
   that did prove necessary got its own changelog entry.

## When done

Changelog and COMPLIANCE row per Claude Code task 2. Then stop. 015 is
the coming-soon landing page and waiting list (see ROADMAP).
