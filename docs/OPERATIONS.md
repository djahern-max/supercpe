# Operations

How supercpe.com is run. Everything here was written with feature 012 and
is the runbook 9.02 leans on: the records the Standards require the
sponsor to keep for five years live in the managed database and the
Spaces bucket, and these procedures are how they stay alive.

## Security posture

- TLS only. Caddy obtains and renews Let's Encrypt certificates; `http://`
  and `www` redirect to `https://supercpe.com`; HSTS is set
  (`max-age=31536000; includeSubDomains`).
- The session cookie is HttpOnly, Secure, SameSite=Lax; passwords are
  argon2id (009). Sessions are server-side random tokens — there is no
  signing SECRET_KEY in this application; revoking sessions means
  deleting rows, not rotating a key.
- Login is rate limited at the proxy: 10 `POST /api/v1/auth/login` per
  minute per client IP (Caddy's rate-limit plugin).
- The Spaces bucket is private. Nothing is served from it directly: video
  plays through presigned GET URLs that expire in one hour
  (`VIDEO_URL_SECONDS`); certificates and audit bundles stream through
  the API behind the session check.
- Secrets live in `/srv/supercpe/.env` on the droplet — mode 600, owned
  by the deploy user, mounted read-only into the api container. They
  appear nowhere in the repo.
- Managed Postgres accepts connections only from the droplet (trusted
  source in the DigitalOcean control panel) with `sslmode=require`.
- The droplet firewall allows inbound 22, 80, 443 and nothing else
  (`ufw allow 22,80,443/tcp` then `ufw enable`, or a DO Cloud Firewall).
- Deliberately not done yet: no WAF, no MFA on accounts, no intrusion
  detection. Recorded so the absence is a decision, not an oversight.

## Who and where (fill these in — they otherwise live in one head)

- DigitalOcean account owner: Dane Ahern (danielaherniv@gmail.com) —
  confirm/correct.
- Where the `.env` values came from: `DATABASE_URL` from the managed
  Postgres cluster's connection details panel; `SPACES_KEY`/`SPACES_SECRET`
  from API → Spaces Keys; the rest per `deploy/env.production.example`.
- Domain registrar for supercpe.com: Namecheap, account `djahern`, using
  Namecheap BasicDNS (`@` and `www` A records → the droplet).
- Uptime monitor and its login: not yet set up as of 2026-08-30 — fill
  in when it exists (alert on non-200 at
  `https://supercpe.com/api/v1/health`, and on `last_backup_at` or
  `last_offsite_backup_at` stale beyond ~26 hours if the monitor can
  match response text — the nightly run is at 03:15 UTC, so ~26 hours
  means one missed night plus slack).
- Off-site provider and its login: not yet chosen as of 2026-08-30 —
  fill in when the bucket exists (provider, account owner, bucket name,
  region, and where the `OFFSITE_*` key was created).

## Layout on the droplet

    /srv/supercpe/.env         secrets (mode 600, deploy user)
    /srv/supercpe/repo         git clone of this repository
    /srv/supercpe/backups      scratch space for nightly dumps (emptied nightly)
    /srv/supercpe/backup.log   backup.sh output, via cron

**Every manual `docker compose ... run` in this runbook starts with**

    cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD)

because `deploy/docker-compose.yml` tags images `${GIT_SHA:-dev}` and
only `deploy.sh` exports `GIT_SHA`. Without the export, a manual command
builds and runs a `dev`-tagged image from whatever is checked out — not
the image serving traffic. The commands below carry the prefix; do not
drop it.

## The PostgreSQL 16 pin

PostgreSQL is pinned to major version 16 in four places that must move
together:

1. `docker-compose.yml` at the repo root (local dev container);
2. the `docker run --rm postgres:16 pg_dump` in `deploy/backup.sh`;
3. the `postgres:16` `pg_restore` in the Restore procedure below;
4. the managed cluster itself (`supercpe-db-prod`, 16.15 as of
   2026-08-30).

DigitalOcean now defaults to **18** and preselects it when creating a
cluster — 16 was a deliberate choice at first deploy to match the
existing pins. The trap: `pg_dump` aborts when the server's major
version is newer than the client's, so a cluster upgraded (or recreated
at the default) without the other three breaks the nightly backup, and
the only signal is `last_backup_at` going stale in `/health`. A major
upgrade is its own maintenance task that changes all four in one go.

## First deploy on a fresh droplet

Executed once for the first production deploy. Prerequisites: the human
tasks in feature 012 (bucket, managed Postgres, droplet, DNS A records
already pointing at the droplet — Caddy cannot obtain a certificate
before DNS resolves).

1. SSH in as root; create the deploy user and give it Docker:
   `adduser deploy && usermod -aG sudo deploy`.
2. Install Docker Engine + compose plugin (`curl -fsSL
   https://get.docker.com | sh`), then `usermod -aG docker deploy`.
3. Firewall: `ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp
   && ufw enable`.
4. As `deploy`: `mkdir -p /srv/supercpe && git clone <repo-url>
   /srv/supercpe/repo`.
5. Copy `deploy/env.production.example` to `/srv/supercpe/.env`, fill in
   the real values by hand (nothing in the repo carries them), then
   `chmod 600 /srv/supercpe/.env`.
6. In the DigitalOcean control panel: add the droplet as a trusted source
   on the Postgres cluster; confirm the `supercpe` database and user
   exist — **and that `supercpe` OWNS database `supercpe`** (`\l supercpe`
   in psql, read the Owner column). The control panel creates the user
   and database without making the user the owner, and since PostgreSQL
   15 the `public` schema is owned by `pg_database_owner`, so a non-owner
   `alembic upgrade head` fails on a permission error that reads like an
   auth problem. The fix, run as `doadmin` connected to `defaultdb`:

       ALTER DATABASE supercpe OWNER TO supercpe;
7. `/srv/supercpe/repo/deploy/deploy.sh main` — builds, migrates the
   empty database to head, starts Caddy and the API, waits for
   `https://supercpe.com/api/v1/health` to report the deployed sha.
   **On the first deploy a non-zero exit at the health poll is
   expected**: the 60-second window also has to cover Caddy's Let's
   Encrypt issuance, and health correctly reports `storage: error`
   until the sentinel is written in step 8. Check `docker compose -f
   deploy/docker-compose.yml ps` and the health body before treating it
   as a failure (the 2026-08-30 first deploy exited exactly this way and
   was healthy after step 8).
8. Write the storage sentinel the health check reads:
   `cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD) && docker compose -f deploy/docker-compose.yml run --rm api python -m app.cli write-sentinel`
9. Create the first admin (password prompted, never a flag):
   `cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD) && docker compose -f deploy/docker-compose.yml run --rm api python -m app.cli create-admin --email <you>`
10. First backup, by hand, so `last_backup_at` is real:
    `/srv/supercpe/repo/deploy/backup.sh`
11. Install the cron entry as the deploy user (`crontab -e`):
    `15 3 * * * /srv/supercpe/repo/deploy/backup.sh >> /srv/supercpe/backup.log 2>&1`
12. Set up the external uptime monitor on
    `https://supercpe.com/api/v1/health` (alert on non-200; if the
    monitor can match response text, also alert when `last_backup_at`
    goes stale by more than ~26 hours). Record the login above.
13. Verify acceptance: the coming-soon page over TLS, `/api/v1/site`
    reporting `coming_soon`, `/login` working with a Secure+HttpOnly
    cookie, `/api/v1/media/anything` returning 404.

## Routine deploy of a tag

1. Push the tag from the laptop: `git tag v0NN && git push origin v0NN`.
2. On the droplet: `/srv/supercpe/repo/deploy/deploy.sh v0NN`.
3. The script is done only when `/api/v1/health` reports the new sha; it
   prints the health body. If it exits non-zero, the old containers may
   still be serving — check `docker compose -f deploy/docker-compose.yml
   ps` and `logs api`.

**If the script stops at `Running preflight ...`** (014a): the new
image ran every check that would refuse boot in prod — the config
validations and the bucket-versioning guard — and printed `preflight
FAILED — the app would refuse to boot:` with the violations listed. The
deploy aborted **before** migrations and before touching the running
containers, so the old version is still serving. This is not an outage;
do not treat it as one. Read the listed violations, fix them (config in
`/srv/supercpe/.env`, or versioning per the Bucket versioning section),
and redeploy. `rollback.sh` execs `deploy.sh`, so a rollback target
passes the same gate.

## Rollback

1. Find the previous sha: `git -C /srv/supercpe/repo log --oneline` or
   the version history in `/api/v1/health` checks.
2. `/srv/supercpe/repo/deploy/rollback.sh <sha>` — a checkout, a rebuild
   from cache (the images are still on disk), a restart, and the same
   health verification.
3. Rollback does **not** undo migrations. Every migration in this repo
   has a downgrade, but each one drops the tables or columns its upgrade
   created — running one destroys retained records (9.02) — so `alembic
   downgrade` is never part of rollback. If an old app version cannot run
   against the new schema, fix forward with a new migration.

## Restore

Two sources, in order of preference:

**From a managed-database snapshot** (whole-cluster, point in time):

1. DigitalOcean control panel → the Postgres cluster → Backups → Restore.
   DigitalOcean restores to a **new** cluster; it does not overwrite.
2. Update `DATABASE_URL` in `/srv/supercpe/.env` to the new cluster
   (keep `sslmode=require`), add the droplet as a trusted source on it.
3. `cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD) && docker compose -f deploy/docker-compose.yml up -d --force-recreate api`
4. Check `/api/v1/health` and spot-check `completions` against
   `certificates/` (below).

**From a nightly dump in `backups/`** (into a scratch database first —
never straight over production):

1. List what exists (prefix per the GIT_SHA note above):
   `cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD) && docker compose -f deploy/docker-compose.yml run --rm api python -c "from app.storage import get_storage; from app.services.backups import dump_dates; print(sorted(dump_dates(get_storage())))"`
2. Download the chosen dump to the droplet:
   `docker compose -f deploy/docker-compose.yml run --rm --user $(id -u) -v /srv/supercpe/backups:/backups api python -c "import shutil; from app.storage import get_storage; s=get_storage(); shutil.copyfileobj(s.open('backups/<DATE>.dump.gz'), open('/backups/restore.dump.gz','wb'))"`
   (same shell, so `GIT_SHA` is still exported). The `--user $(id -u)`
   matters: the api container runs as non-root and is writing into a
   host mount, so without it the copy fails with `PermissionError`.
3. Create a scratch database on the cluster (control panel or `createdb`),
   then:
   `gunzip -c /srv/supercpe/backups/restore.dump.gz | docker run --rm -i postgres:16 pg_restore --no-owner -d "<postgresql://...scratch db url>"`
   This works from the droplet even though the cluster only trusts the
   droplet: container traffic NATs through the droplet, which is the
   cluster's trusted source — do not add a Cloud Firewall rule for it.
   **URL scheme:** `DATABASE_URL` in `.env` is `postgresql+psycopg://…` —
   a SQLAlchemy dialect URL that `pg_restore` and `psql` reject. Build a
   plain `postgresql://…` URL for these tools. The plain-scheme URL is
   for `pg_restore`/`psql` on the command line only and must **never**
   be written into `.env` (step 7 records what happens if it is).
   When assembling it from the control panel, use the password field's
   **copy icon**, not a mouse selection: the `show` link becomes `hide`
   immediately beside the revealed password, so a selection captures a
   trailing `hide` and psql fails with a percent-encoded-spaces error.
   Ownership trap, same as first-deploy step 6: a panel-created database
   is owned by `doadmin`, so either restore as `doadmin` or run
   `ALTER DATABASE <scratch> OWNER TO supercpe` first.
4. Verify the restore lines up with the bucket: every
   `completions.certificate_key` in the scratch database should exist
   under `certificates/` in Spaces
   (`SELECT certificate_key FROM completions WHERE certificate_key IS NOT NULL`
   against `storage.exists(...)`).
5. Verify the restore against production directly — these checks are not
   vacuous even when the database is empty (an empty match is still a
   match; record it as such). Run each command twice, once with the
   scratch URL and once with the production URL (both plain
   `postgresql://` scheme per step 3), and compare the outputs:

       docker run --rm postgres:16 psql "<url>" -tAc \
           "SELECT version_num FROM alembic_version"
       docker run --rm postgres:16 psql "<url>" -tAc \
           "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
       docker run --rm postgres:16 psql "<url>" -tAc \
           "SELECT count(*) FROM accounts"

6. Cleanup — **a drill ends here**; step 7 belongs to a real recovery
   only. Delete the downloaded dump
   (`rm /srv/supercpe/backups/restore.dump.gz`), drop the scratch
   database (control panel or `dropdb`), and confirm
   `/srv/supercpe/.env` still contains exactly one `DATABASE_URL`,
   pointing at database `supercpe`, with the `postgresql+psycopg://`
   scheme.
7. **Real recovery only — never part of a drill.** Only after the step
   4–5 verifications, either point `DATABASE_URL` at the scratch
   database or `pg_restore` into the real one, then repeat the cleanup
   in step 6. During the 2026-08-30 drill this step, as previously
   written, was followed as if it were the next step and left
   production's `.env` pointing at the scratch database (which the drill
   then deleted) with a plain `postgresql://` scheme. The site stayed up
   only because running containers keep the config they started with;
   the next `deploy.sh` failed at the migration step with
   `ModuleNotFoundError: No module named 'psycopg2'`, because the plain
   scheme makes SQLAlchemy default to the psycopg2 driver.

**Restore drill record** (required by 012 before launch; repeat yearly):

| Date | Source | Time taken | Verified by |
|------|--------|-----------|-------------|
| 2026-08-30 | `backups/2026-08-30.dump.gz` → scratch db `supercpe_restore_drill` | 18 min | Dane Ahern |

**Bucket-layer recovery drill record** (013's acceptance 7; record its
date here when run): overwrite `health/sentinel` by running
`write-sentinel` twice, list the key's versions, recover the older by
`VersionId` per the Bucket versioning section below.

| Date | Verified by |
|------|-------------|
| _not yet performed_ | |

## Bucket versioning

Object versioning on `supercpe-prod-nyc3` (013) keeps every prior
version of a retained object, so an accidental overwrite or delete at
the bucket layer is recoverable. It is enabled once by
`python -m app.cli bucket-setup` (014a — the logic moved into the api
image from `deploy/bucket-setup.py`, which proved unrunnable from the
droplet: no host Python, not in the image, and a bind-mount broke its
path bootstrap). It runs as a one-off api container, so boto3 and the
`app` package are simply present and the bucket, region, and endpoint
come from the mounted `.env` — no mounts beyond the normal one, no host
Python, no path tricks:

    cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD)
    read -rs SETUP_SPACES_KEY && read -rs SETUP_SPACES_SECRET
    export SETUP_SPACES_KEY SETUP_SPACES_SECRET
    docker compose -f deploy/docker-compose.yml run --rm \
      -e SETUP_SPACES_KEY -e SETUP_SPACES_SECRET \
      api python -m app.cli bucket-setup

**The key**: DigitalOcean console → Spaces Object Storage → Access
Keys → Create Access Key → **All Permissions**. Do **not** scope the
key to the bucket: a bucket-scoped key gets `AccessDenied` on
`PutBucketVersioning` even with full object rights — only an All
Permissions (all-buckets) key can make bucket-configuration calls.
(This distinction cost real debugging time on 2026-08-30, when this
runbook said only "temporary Full Access key".) `read -rs` keeps the
secret out of shell history. As soon as both read-backs print: delete
the key in the console, then
`unset SETUP_SPACES_KEY SETUP_SPACES_SECRET`.

The same run sets the one lifecycle rule: noncurrent versions under
`backups/` expire after `BACKUP_NONCURRENT_DAYS` (7) days; no other
prefix has any rule — `packages/`, `certificates/`, and `audits/`
versions are never expired. The command reads both back and exits
non-zero if the bucket does not report them as set.

**Real-run read-back record** (the evidence for whether DigitalOcean
honors `NoncurrentVersionExpiration` with a prefix filter — 013's open
question; paste both read-backs, dated, when the command runs against
the real bucket):

| Date | versioning read-back | lifecycle read-back | Run by |
|------|----------------------|---------------------|--------|
| _not yet run_ | | | |

The runtime Limited Access key can *read* the versioning status but
cannot change versioning or lifecycle — that is the point: in `prod` the
app refuses to boot while versioning is not `Enabled`, and `/health`
reports `bucket_versioning: error` (a 503) if it is ever suspended
afterwards. Until `bucket-setup` has run, `deploy.sh`'s preflight gate
refuses to deploy 013 or later — the old version keeps serving
(a preflight abort, not an outage; see Routine deploy above).

**To recover a prior version of an object** (with any key that can read
the bucket; restoring needs write):

    # list the versions of a key
    aws s3api list-object-versions --bucket supercpe-prod-nyc3 \
        --prefix <key> --endpoint-url https://nyc3.digitaloceanspaces.com
    # download the version you want by VersionId
    aws s3api get-object --bucket supercpe-prod-nyc3 --key <key> \
        --version-id <VersionId> restored-file \
        --endpoint-url https://nyc3.digitaloceanspaces.com

Then put the recovered bytes back as a new write (a new current
version); never delete the bad version — the history is the control. A
deleted key is recovered the same way: its versions are still listed
under a delete marker.

## Off-site copy

The second copy of the 9.02 records (013) lives in an S3-compatible
bucket at a **different provider**, so a DigitalOcean-level failure
(account lockout, region loss, billing lapse) cannot take the originals
and every backup together.

- Provider, bucket, region, and account login: see "Who and where"
  above (fill in when chosen).
- The `OFFSITE_*` values in `/srv/supercpe/.env` come from that
  provider: an application key scoped to the one bucket,
  read/write/delete. All five variables or none
  (`deploy/env.production.example` documents them).
- What is mirrored, nightly by `deploy/backup.sh` via
  `python -m app.cli mirror-offsite`: that night's dump under
  `backups/`, a `backups/LATEST` stamp, and every object under
  `certificates/` and `audits/` that is absent or changed off-site.
  Nothing is ever deleted off-site. `packages/` is **not** mirrored:
  videos are large and every exported zip also exists in video-tool's
  `dist/` on the machine that produced it.
- On success the primary bucket gets `backups/OFFSITE`, which `/health`
  reports as `last_offsite_backup_at` — stale beyond ~26 hours means the
  mirror is failing (check `/srv/supercpe/backup.log`; the off-site step
  is named in it). An off-site failure exits non-zero **after** the
  primary backup is stamped, so it can never mask a primary failure.

**To restore a dump from the off-site copy**: same `pg_restore` path as
the Restore section above; only the download step differs — fetch the
dump from the off-site bucket instead of Spaces:

    aws s3 cp s3://<offsite-bucket>/backups/<DATE>.dump.gz \
        /srv/supercpe/backups/restore.dump.gz \
        --endpoint-url <OFFSITE_ENDPOINT>

(credentials: the `OFFSITE_*` key from `.env`, e.g. via
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`). Then continue from step 3
of the dump-path restore. The drill for this path is a Phase C item.

## Rotate a secret

**Spaces key:** DigitalOcean → API → Spaces Keys → create a new key
scoped to the bucket; put it in `/srv/supercpe/.env`; `cd
/srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD) && docker
compose -f deploy/docker-compose.yml up -d --force-recreate api`; confirm
`/health` storage is `ok`; delete the old key. Presigned URLs signed by
the old key die with it — an hour's worth of play URLs at most.

**Database password:** control panel → cluster → Users → reset password;
update `DATABASE_URL` in `/srv/supercpe/.env`; recreate the api container
as above; confirm `/health` database is `ok`.

**Session secret:** there is none to rotate — sessions are server-side
random tokens (009). The equivalent gesture is revoking every session:
`cd /srv/supercpe/repo && export GIT_SHA=$(git rev-parse HEAD) && docker
compose -f deploy/docker-compose.yml run --rm api python -c
"from app.db import SessionLocal; from sqlalchemy import text;
db=SessionLocal(); db.execute(text('DELETE FROM sessions')); db.commit()"`
— everyone is signed out and signs in again.

## Re-ingest a course

Production started from an empty database by design; ASC842-PCX (or any
course) arrives the same way it did in development:

1. Sign in as admin at `https://supercpe.com/login`.
2. Upload each exported package zip (`ASC842-PCX-01.zip` … `-04.zip`) at
   the admin packages page; each lands under `packages/` in the bucket.
3. Create the draft course, attach the packages in manifest order.
4. Enter the SME records and record the content review for real (008) —
   development's fictitious reviewer never leaves the laptop.
5. Publish when readiness reports no block findings.

## The waiting list (015)

While `site_mode` is `coming_soon`, the public site is the landing page
and its waiting-list form. The entries are not CPE records — no
retention floor applies, and Remove honors an off-the-list request
immediately (a soft delete; the row leaves every count, listing, and
export).

- **Count and entries**: sign in as admin, `/admin/waiting-list` —
  total, searchable table, per-row Remove.
- **Export**: the "Export CSV" button on that page, or
  `GET /api/v1/admin/waiting-list/export.csv` with an admin session.
  UTF-8, header row, ISO-8601 timestamps; active entries only. This
  file is what 021's invitations will be fed from — it is generated on
  request, not written to Spaces, and is not part of any audit bundle.
- **Closing**: flipping `site_mode` to `open` 404s both public routes
  (`GET /api/v1/landing`, `POST /api/v1/waiting-list`) and closes
  submissions **permanently** — the list is only ever open before
  launch. The admin page and export keep working in either mode.
- Signups are rate limited at the proxy like login: 10
  `POST /api/v1/waiting-list` per minute per client IP, plus a hidden
  honeypot field answered with a normal 200 that stores nothing.

## Outbound email (017)

The app sends email through one service with two backends chosen by
`EMAIL_BACKEND`: `console` (dev/test — the message goes to the app log
and the `email_message` table, no network) and `smtp` (production —
generic SMTP with STARTTLS). The code is provider-agnostic on purpose:
choosing a provider is this runbook's decision, recorded here when made.

**Provider: not yet chosen.** Record the provider, the account owner,
and where the credentials live when the choice is made.

To configure production email:

1. Choose an SMTP provider and create credentials for a
   `no-reply@supercpe.com` (or similar) sender. Set up SPF/DKIM for the
   domain per the provider's instructions so verification email lands
   in inboxes.
2. Set all six variables in the production env: `EMAIL_BACKEND=smtp`,
   `EMAIL_HOST`, `EMAIL_PORT` (587 for STARTTLS), `EMAIL_USERNAME`,
   `EMAIL_PASSWORD`, `EMAIL_FROM`. They are all-or-nothing: a partial
   set refuses to boot (`python -m app.cli preflight` catches it before
   the deploy does).
3. Prove the config before relying on it: sign in as admin, open
   `/admin/sponsor`, and use **Send test email** — it delivers to your
   own admin address through the configured backend and logs an
   `email_message` row. A 502 with the SMTP error means the config is
   wrong; nothing else in the site is affected.
4. Only then flip `coming_soon → open`. The flip **refuses** while
   `EMAIL_BACKEND` is not `smtp` or any `EMAIL_*` is unset — an open
   site with a registration form that cannot send verification email
   would be lying to the public. Absent email config is a valid state
   only while the site is coming-soon.

The `email_message` table logs kind, recipient, subject, and backend for
every send — never the body. These are operational records, not CPE
records; no retention floor applies.

## Payments (018)

Stripe holds the card on its hosted Checkout page; superCPE never sees
card data and holds only the paper trail (`payments` table, admin
`/admin/payments`). The webhook is the sole creator of enrollments — a
browser landing on the success page proves nothing — so the webhook
endpoint and its signing secret are load-bearing: without them, people
pay and no enrollment appears.

To configure payments:

1. Create the Stripe account (owner and credential location recorded
   here when done, like email). In Stripe settings, enable **Successful
   payments** customer emails — Stripe sends the receipt; superCPE
   sends no payment email of its own.
2. Create a **restricted** API key (not the full secret key) with write
   access to Checkout Sessions only; that is all the app calls.
3. Register the webhook endpoint
   `https://supercpe.com/api/v1/stripe/webhook` in the Stripe dashboard
   for the events `checkout.session.completed`,
   `checkout.session.expired`, and `charge.refunded`, and capture its
   signing secret (`whsec_…`).
4. Set all three variables in the production env: `STRIPE_SECRET_KEY`
   (the restricted key), `STRIPE_PUBLISHABLE_KEY`,
   `STRIPE_WEBHOOK_SECRET`. All-or-nothing: a partial set refuses to
   boot (`python -m app.cli preflight` catches it). Absent entirely is
   valid only while the site is coming-soon.
5. Test-mode end-to-end on the dev machine before trusting any of it:
   put the test-mode keys in the local `.env`, run
   `stripe listen --forward-to localhost:8000/api/v1/stripe/webhook`
   (the CLI prints a test `whsec_…` — use it as
   `STRIPE_WEBHOOK_SECRET`), buy a published course with card
   `4242 4242 4242 4242`, and watch the success page flip to enrolled
   when the forwarded webhook lands. `stripe trigger
   checkout.session.completed` exercises the handler without a browser.
6. The `coming_soon → open` flip **refuses** while any `STRIPE_*` is
   unset (`payments_not_configured`) — an open catalog whose Enroll
   buttons cannot reach Stripe would be lying. Publish likewise refuses
   a course with no price (a business rule, not a Standards item).

**Refund runbook.** Do the refund in the Stripe dashboard (there is no
refund button in superCPE, deliberately). The `charge.refunded` webhook
marks the payment `refunded`, and `/admin/payments` flags
**refunded with active enrollment** loudly. Then decide per the
published refund policy whether access ends: if it does, use **Void
enrollment** on that row (logged — who and when are stamped on the
enrollment; the participant's row and progress are kept, never
deleted). Nothing voids automatically, because a refund after credit
was earned or a certificate issued is a policy decision, not a
mechanical one. Completed enrollments cannot be voided at all — the
completion is an immutable 9.02 record.

Payments rows are financial records: never deleted, not subject to the
five-year CPE retention floor — they outlive it.

## When /health goes red

The monitor alerts on non-200. Fields, in the order to check:

- `database: error` — the API cannot reach the managed cluster. Check
  the cluster's status page in the control panel, then the trusted-source
  list (a rebuilt droplet has a new IP), then `DATABASE_URL` in
  `/srv/supercpe/.env`. `docker compose logs api` shows the driver error.
- `storage: error` — the sentinel HEAD failed: Spaces outage, deleted or
  rotated key, or someone deleted `health/sentinel`. Re-run
  `python -m app.cli write-sentinel` (inside the api container, with the
  GIT_SHA prefix from the note above) after fixing credentials; if the
  sentinel object itself was the casualty, that command is the whole fix.
- `ffprobe: error` — the image is broken (ffmpeg is installed by the
  Dockerfile); a deploy with a modified Dockerfile is the likely cause.
  Roll back.
- `bucket_versioning: error` — someone suspended versioning on the
  bucket, or the versioning read itself failed. Nothing in the runtime
  can have done it (the Limited Access key cannot change versioning);
  check who touched the bucket, then re-enable with
  `python -m app.cli bucket-setup` per the Bucket versioning section.
- `last_backup_at` stale (not a 503 by itself) — the nightly backup
  failed. `tail /srv/supercpe/backup.log`; run
  `/srv/supercpe/repo/deploy/backup.sh` by hand and watch it.
- `last_offsite_backup_at` stale or null (not a 503 by itself) — null
  means `OFFSITE_*` is unconfigured or no mirror has ever succeeded;
  stale means the off-site provider or its key is the problem. The
  backup log names the off-site step; the primary backup is unaffected
  either way.
- Whole endpoint unreachable — Caddy or the droplet. `docker compose -f
  deploy/docker-compose.yml ps`, then `logs caddy`; then the droplet
  console in the control panel.
