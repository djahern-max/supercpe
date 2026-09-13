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
- Clearing the session cookie in a browser signs that browser out but
  leaves its `sessions` row valid until the idle or absolute expiry. The
  Sign out button (025, in the site header and the admin nav) posts to
  `POST /api/v1/auth/logout`, which revokes the row; a tester who has
  been clearing cookies instead has left live rows behind.
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
3. The script is done only when `/api/v1/health` reports the new sha
   **with a 2xx**; it prints the health body. A non-zero exit is one of
   two things, and the last line says which (023c, `deploy/wait-for-health.sh`):
   - `New version <sha> running, unhealthy (HTTP 503): storage` — the
     new containers are serving and a component is red; the names are
     read from the health body. For `storage`, the API now logs why:
     `docker compose -f deploy/docker-compose.yml logs api | grep "health storage check failed"`
     prints the exception class and message (query strings are cut, so
     no signed URL reaches the log). A missing sentinel names itself and
     the `write-sentinel` command that fixes it. Exit code 1.
   - `Health never reported <sha> — the old version may still be running`
     — the sha was never seen in the 60-second window; check `docker
     compose -f deploy/docker-compose.yml ps` and `logs api`. Exit code 2.

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

026 made the transport provable **before** the flip: the webhook route
answers while the site is `coming_soon` (the one route exempt from the
009 gate — it discloses nothing, and an unsigned request gets the same
bare 400 in either mode), sandbox keys are valid config on a closed
site, and two checks (below) make it impossible to open on them. Every
payment row records Stripe's own `livemode`, so a sandbox transaction
stays in the record, honestly marked, and is never deleted.

### Account and keys

Recorded as the steps to execute, in order. Tick each with its date in
the log at the end of this section when done.

1. **Create the Stripe account** as the LLC: legal name and EIN exactly
   as on the IRS letter, the registered business address, industry
   "Education — professional training" (or the closest Stripe offers),
   website `https://supercpe.com`. Record the account owner and where
   the login lives in "Who and where" above. In Stripe settings enable
   **Successful payments** customer emails — Stripe sends the receipt;
   superCPE sends no payment email of its own.
2. **Statement descriptor** = `sponsor_profile.name` exactly as
   `/admin/sponsor` shows it (Stripe allows 5–22 characters, no
   `< > ' " *`). A CPA who does not recognize the charge on a card
   statement disputes it, and one dispute costs more than the course.
   The descriptor must be the name they saw on the site and will see on
   the certificate.
3. **Keys.** Every Stripe account has a sandbox (test mode) beside live
   mode, each with its own keys. `STRIPE_SECRET_KEY` is a **restricted**
   key in both modes, never the full secret key. Create the live key
   with exactly these scopes, so launch day is copy-work:
   - Checkout Sessions — **Write** (what `create_checkout_session` calls)
   - Payment Intents — **Read**
   - Charges — **Read**
   - Refunds — **Read**
   - everything else — None

   The three reads are for the dashboard-side look the refund runbook
   asks for and cost nothing to grant. If Stripe refuses session
   creation with a permissions error naming Products or Prices, add
   Products **Write** — inline `price_data` creates them. The
   publishable key (`pk_…`) is not secret and has no scopes.
   **029 adds the Billing scopes** — see "Subscriptions (029)" below;
   the same key carries both sets.

   **State on 2026-09-12:** the sandbox deployment on production runs on
   the Stripe **standard** secret key (`sk_test_…`), not a restricted
   key; no restricted key exists in the sandbox. That is tolerable for
   the sandbox only. Live must never run on the standard key — the
   opening-day checklist (step 4) creates the live restricted key with
   the union of the 018 and 029 scopes before the swap.
4. **Register the webhook endpoint — twice.** URL
   `https://supercpe.com/api/v1/stripe/webhook`; events
   `checkout.session.completed`, `checkout.session.expired`,
   `charge.refunded`, plus the four Billing events 029 added
   (`customer.subscription.updated`, `customer.subscription.deleted`,
   `invoice.paid`, `invoice.payment_failed`). Register it once in the
   **sandbox** (for the verification run below) and again, separately,
   in **live mode** at flip time. **They have different signing secrets.
   `STRIPE_WEBHOOK_SECRET` must be swapped in the same edit as the two
   keys and the price id.** With live keys
   and the sandbox secret, every live event fails signature
   verification: the Stripe dashboard shows delivery attempts answered
   400, the site shows nothing, and people who paid have no enrollment.
   This is the single most likely launch-day failure, and no code can
   catch it — signing secrets carry no live/test prefix. Before the
   flip also check that Stripe has not **disabled** the sandbox
   endpoint: Stripe disables endpoints after sustained delivery
   failures, and one that sat idle-and-failing is the warning that the
   live one can go the same way. The status is on the endpoint's
   dashboard page; do not assume it.
5. **Set the four variables** in `/srv/supercpe/.env`:
   `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`,
   and (029) `STRIPE_SUBSCRIPTION_PRICE_ID`. All-or-nothing: a partial
   set refuses to boot (preflight catches it). Absent entirely is valid
   only while coming-soon. Sandbox values are valid while coming-soon;
   live values are required to open. Price ids differ between sandbox
   and live mode exactly as the keys do.
6. **Run the production verification** (below) with the sandbox values,
   before the flip.
7. **At the flip**, swap all four values to live in one edit, deploy,
   open the site, and make the one live smoke purchase (Opening day
   step 8).

### What refuses what (026)

Two checks, two questions. Detection is by key prefix only
(`sk_live_` / `pk_live_`); nothing calls Stripe from a validator.

- **The open gate.** `coming_soon → open` is refused — 422
  `{"errors": [...]}`, shown on `/admin/sponsor` as the
  `payments_test_keys` block finding — while `STRIPE_SECRET_KEY` does
  not start with `sk_live_` or `STRIPE_PUBLISHABLE_KEY` with `pk_live_`.
  One message per offending variable:

      STRIPE_SECRET_KEY is not a live Stripe key (expected the sk_live_
      prefix); an open site must charge real cards (026). Swap all four
      STRIPE_* settings to the live values in one edit, the webhook
      signing secret and the subscription price id included.

  018's `payments_not_configured` finding still fires instead when any
  of the four is unset. This is the check that matters: the flip is
  the moment test keys become dangerous.
- **Preflight.** `python -m app.cli preflight` — run by `deploy.sh`
  before migrations, old version still serving — fails when the site is
  **already open** and either key is not live-prefixed:

      STRIPE_SECRET_KEY is not a live Stripe key (expected the sk_live_
      prefix) and the site is open: this deploy would put test keys on a
      live catalog. Swap all four STRIPE_* settings to the live values
      in one edit, the webhook signing secret and the subscription price
      id included.

  So the failure mode is a refused deploy, not an outage. While
  coming-soon it says nothing about keys. If it cannot read `site_mode`
  (first deploy, no tables yet) it prints a note and skips — there is
  no open site to protect.
- **Neither checks `STRIPE_WEBHOOK_SECRET`.** It cannot be checked by
  prefix; step 4's swap rule is the control. A cheap future check would
  compare `livemode` on the first received event against the key
  prefix and log loudly on mismatch; noted, not built.
- **Preflight also checks the subscription price (029).** One
  `Price.retrieve` of `STRIPE_SUBSCRIPTION_PRICE_ID`: on an open site a
  Price whose amount or currency differs from `SUBSCRIPTION_PRICE_CENTS`
  (or a Price that cannot be read) refuses the deploy, naming both
  numbers; while coming-soon it prints a note. See "Subscriptions
  (029)".

### Production verification run (026)

An operator procedure, not a test: a complete sandbox checkout against
the live server — real DNS, real TLS, real Caddy routing, real
signature verification — while `site_mode` is still `coming_soon`.
Nothing about the transport needs live money.

1. `/srv/supercpe/.env` gains the three **sandbox** values. Site stays
   `coming_soon`.
2. Deploy. Preflight passes — the site is not open, so the live-key
   check is silent.
3. Register the sandbox webhook endpoint at the production URL (step 4
   above). Send a test event from the dashboard. Expect **200**, not 404;
   an unsigned probe (`curl -X POST https://supercpe.com/api/v1/stripe/webhook`)
   answers 400 `{"detail":"Invalid webhook signature"}`.
4. Sign in as a participant (any session passes the closed gate), buy a
   published course with `4242 4242 4242 4242`.
5. Confirm on `/admin/payments`: the row goes `pending → paid` and shows
   the **Test** marker (`livemode = false`); exactly one enrollment
   exists with a one-year expiry; `/purchase/success` stops polling and
   links to the player.
6. Replay the event from the dashboard. Nothing changes (idempotent by
   event id).
7. Refund in Stripe. The payment goes `refunded`, the enrollment
   survives, the refunded-with-active-enrollment flag appears. **The
   flag is not a bug** — see the refund runbook.
8. Void the test enrollment with the admin action. The payment row
   stays: it is an honest record of a test transaction, and `livemode`
   says so.
9. Attempt `coming_soon → open` on `/admin/sponsor`. It **must refuse**,
   naming `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` as not live.
   This step is what proves 026 did both of its jobs.
10. Remove the three values from `.env`, deploy, confirm `/health` green.
    (Or leave the sandbox values in place until the flip; either is
    valid while coming-soon.)

Log — one line per run, newest last:

| Date | Who | Outcome |
| --- | --- | --- |
| 2026-09-11 | — | **Not yet run.** 026 shipped the code and this procedure; the run needs the Stripe sandbox keys, the dashboard, a browser, and the droplet, none of which the build session had. Record the first run here and in a new CHANGELOG entry. |
| 2026-09-12 | operator | A $29.00 test-mode Checkout completed on production at 11:56 AM local: `checkout.session.completed` for `pi_3UEpY1GWw04RDXCn0rkCWIIS`; the production webhook destination shows 1 delivery, 0 failed, 416 ms. Evidence for steps 3–5. Whether this was the full walkthrough (steps 6–10) is confirmed in the 026 verification CHANGELOG entry, written after that confirmation. |

### Refund runbook

Do the refund in the Stripe dashboard (there is no refund button in
superCPE, deliberately). The `charge.refunded` webhook marks the payment
`refunded`, and `/admin/payments` flags **refunded with active
enrollment** loudly. **That flag is not a bug**: nothing voids
automatically, because a refund after credit was earned or a
certificate issued is a policy decision, not a mechanical one. Then
decide per the published refund policy whether access ends: if it
does, use **Void enrollment** on that row (logged — who and when are
stamped on the enrollment; the participant's row and progress are kept,
never deleted). Completed enrollments cannot be voided at all — the
completion is an immutable 9.02 record.

Payments rows are financial records: never deleted, not subject to the
five-year CPE retention floor — they outlive it. Test-mode rows
(`livemode = false`, the quiet **Test** marker, dashboard link into the
sandbox) are kept on the same terms; nothing hides or removes them.

## Subscriptions (029)

The annual subscription: $149 (`SUBSCRIPTION_PRICE_CENTS`), a Stripe
Billing subscription started through Checkout in `subscription` mode,
auto-renewing yearly, unlimited course enrollments while current. Stripe
owns the schedule and the card; superCPE owns the paper trail
(`subscriptions`, `subscription_invoices`, `payments.credited_to_subscription_id`)
and the entitlement (`services/subscriptions.py:current` — status
`active` and now before `current_period_end`, both as Stripe last
reported them; `past_due` is **not** current, and there is no grace
period). It rides the same account, keys, and webhook endpoint as 018.
**Prerequisite:** the 026 production verification run (above) logged
as passed before this is deployed.

### Setup

Recorded as the steps to execute, in order; tick each in the log at the
end of this section.

1. **Create the Product and the yearly Price** in the dashboard (once
   in the sandbox, once in live mode): Product "superCPE annual
   subscription", one recurring Price, **yearly**, **USD 149.00**,
   currency `usd`. The Price amount must equal `SUBSCRIPTION_PRICE_CENTS`
   in `backend/app/constants/subscription.py` — the page displays the
   constant, Stripe charges the Price, and preflight refuses an open
   site where they differ (naming both numbers). Set
   `STRIPE_SUBSCRIPTION_PRICE_ID=price_…` in `/srv/supercpe/.env`; it
   is the fourth member of the all-or-nothing STRIPE_* group and is
   swapped to the live value in the same edit as the keys.

   **Done in the sandbox, 2026-09-12:** Product "superCPE annual
   subscription" and yearly Price `price_1UEtb2GWw04RDXCnRbBgU2KL`
   ($149.00 USD/year) created; `STRIPE_SUBSCRIPTION_PRICE_ID` set on
   production to that id. **The Price is mode-specific**: a live Product
   and Price do not exist yet and are created at the flip (Opening day
   step 4). The open gate checks that the id is present and preflight
   checks its amount; neither checks the mode, so a sandbox id left in
   place on an open site fails only on the first live subscribe.
2. **Add the Billing scopes to the restricted key** (both modes), on
   top of 018's: Customers — **Write** (one Customer per account,
   created on the first subscribe); Subscriptions — **Read** (one
   retrieve per completed session); Coupons — **Write** (the
   per-account credit coupon); Billing Portal — **Write** (sessions);
   Invoices — **Read**; Prices/Products — **Read** (preflight's
   `Price.retrieve`). As the dashboard names them; if a call is refused
   with a permissions error naming a resource, add that one.
3. **Register the four new event types on both webhook endpoints**
   (sandbox and live): `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.paid`,
   `invoice.payment_failed`. `checkout.session.completed` and
   `charge.refunded` are already registered and now carry subscription
   sessions and invoice refunds too. `customer.subscription.created` is
   deliberately not needed: the completed-session handler retrieves the
   subscription once and copies status and period from it.

   **State on 2026-09-12:** the sandbox destination
   `we_1UEpAaGWw04RDXCnayTHkdSn` listens to all seven events
   (`charge.refunded`, `checkout.session.completed`,
   `checkout.session.expired`, `customer.subscription.deleted`,
   `customer.subscription.updated`, `invoice.paid`,
   `invoice.payment_failed`). The **live** destination still needs the
   four 029 events added (Opening day step 4).
4. **Configure the Customer Portal** (Settings → Billing → Customer
   portal), both modes: cancellation **allowed, at period end**
   (immediate cancellation off); payment method update **allowed**;
   invoice history **on**; plan switching **off**; quantity changes
   **off**. Return URL is set per session by the app (`/account`).
   Cancellation, card update, and invoice history live in the portal;
   superCPE builds none of them.
5. **Enable Stripe's dunning emails** (Settings → Billing →
   Subscriptions and emails): failed-payment emails to the customer on,
   with Stripe's default retry schedule. superCPE sends no billing
   email of its own — the same posture as 018's receipt email. On a
   failed renewal Stripe moves the subscription to `past_due`; the
   participant's `/account` says "update your payment method" and the
   entitlement is off until `invoice.paid` lands and Stripe moves it
   back to `active`.
6. **Stripe Tax** applies to subscriptions exactly as the 018 ROADMAP
   note describes for courses: if it is enabled on the account, enable
   automatic tax on the Checkout Session (a code change; not built).

### Test-mode walkthrough (Stripe CLI)

With the sandbox values in `.env` and `stripe listen --forward-to
localhost:8000/api/v1/stripe/webhook` running (its signing secret in
`STRIPE_WEBHOOK_SECRET`):

1. **Subscribe with credit.** Sign in as a participant who bought two
   courses (018's walkthrough, twice). Open `/subscribe`: it says
   "$58 credited: you pay $91 today" (two $29 courses) or the amounts
   at hand. Subscribe with `4242 4242 4242 4242`. `/subscribe/success`
   stops polling once `checkout.session.completed` lands; `/account`
   shows the renewal date and the credit consumed; `/admin/subscriptions`
   shows the row `active` with `credit_applied_cents` equal to the
   discount Stripe reported, and `/admin/payments` marks both course
   payments "credited to subscription #N".
2. **Subscribe without credit** (a fresh participant): pays the full
   price, no coupon. Confirm a second `/subscribe` while the first
   session is still open returns the same session URL.
3. **Enroll.** On a course page the subscriber sees one button, "Enroll
   (included in your subscription)". Click: the enrollment appears on
   `/my/courses` with a one-year expiry, with no Stripe activity. Buying
   another course is refused ("your subscription covers this course").
4. **Renew.** `stripe trigger invoice.paid` (or advance the test clock
   on the subscription in the dashboard): a second row under Invoices on
   `/admin/subscriptions`, and the period end moves.
5. **Cancel via the portal.** `/account` → Manage subscription → cancel.
   `/account` says "cancels on <date>"; at period end (test clock) the
   status goes `canceled`, the entitlement ends, and the enrollment
   started under it is untouched and still active.
6. **Refund.** Refund the first invoice's charge in the dashboard. The
   invoice row goes `refunded`; `/admin/subscriptions` raises both
   flags. Nothing is voided or cancelled. See the runbook below.

Log — one line per run, newest last:

| Date | Who | Outcome |
| --- | --- | --- |
| 2026-09-12 | — | **Not yet run.** 029 shipped the code and this procedure; the run needs the sandbox keys, the dashboard, the CLI, and a browser. Record the first run here and in a new CHANGELOG entry. |

### Refund runbook (subscriptions)

Full refund, no questions asked, never pro-rata. In order:

1. **Refund the invoice** in the Stripe dashboard (the charge behind
   the current period's invoice). `charge.refunded` marks the invoice
   row `refunded` and **stops** — no status change, no voiding.
2. **Cancel the subscription** in the Stripe dashboard (immediately,
   not at period end — the money is back). `customer.subscription.deleted`
   syncs the status to `canceled` here and the entitlement ends; the
   "refunded with current subscription" flag clears.
3. **Watch the second flag**: "refunded with active enrollments" lists
   the enrollments started under the subscription that are still
   active. Per the published refund policy, access to in-progress
   enrollments ends on a refund: press **Void enrollment** on each
   (018's action — logged, deactivate-never-delete). Completed
   enrollments and issued certificates are immutable 9.02 records a
   refund cannot unmake; they stay, and that is an accepted sponsor
   exposure recorded in the 029 changelog entry.
4. Rows stay: the subscription, its invoices, the credit marks on the
   course payments, and the voided enrollments are all financial or
   participant records, never deleted. **The flags are not bugs**; they
   are the queue of decisions this runbook answers.

## Certificate delivery (019)

On completion the participant gets one email (kind `certificate`) with
their certificate PDF attached, through the same 017 email backend as
everything else. The email is a courtesy layered on the record: the
participant can always download from their account, and nothing about
delivery can touch the completion or the certificate.

`delivery_status` on each completion (the Delivery column of the admin
course page's Completions table):

- **sent** — the backend accepted the message; `delivered_at` says when.
- **pending** — no send has been attempted: the completion predates 019,
  or the sponsor's issuance fields still block the render (fix those on
  `/admin/sponsor`, then Resend).
- **failed** — the send was refused. Nothing retries automatically, by
  design: the table flags it and **Resend email** is the recovery. Resend
  renders the PDF first if needed, sends again, and updates the status.
  If it keeps failing, the email backend is the problem — see Outbound
  email (017); the admin test email is the quick check.

Verification is public by design. Every certificate prints a code and
anyone holding it — a state board, an employer — can confirm the
certificate at supercpe.com/certificates/verify. The page serves only
what the certificate itself says, frozen at completion; unknown and
malformed codes get one identical not-found answer, and the lookup is
rate limited in Caddy like the other anonymous routes. Do not treat a
verification code as a secret — it identifies one certificate, grants
nothing, and is meant to be handed out.

## Jurisdiction policies (020)

`/admin/jurisdictions` holds one row per US licensing jurisdiction: the
board's accepted credit increment, any non-technical cap (quoted, never
computed), the source the rule was read from, and the date it was
verified. The table ships empty on purpose and **filling it is Dane's
research responsibility** — every fact a participant sees is one a human
checked against a board source on a date.

A row reaches participants (the "For your board" panel on course pages)
only when it is **Displayable**: increment set (not Unknown), source
filled, verification date set. Anything less shows nothing — no stub, no
"check back later". Participants opt in by setting their state of
licensure on their account page; nothing is shown to anyone else, and
nothing from this table ever reaches a certificate.

Rows verified more than 12 months ago get a **Re-verify** nudge in the
admin table. Once a year (or when a board announces a rule change),
re-read the source, update the row if the rule moved, and set the
verification date to today. Boards of accountancy keep final authority
on acceptance of CPE credits; the panel says so in a fixed sentence and
these rows must never be written as if superCPE were speaking for a
board.

## Waiting-list invitations (021)

Everyone on the waiting list was promised exactly one email: the site is
open, here is where to register. `/admin/waiting-list` has the
Invitations panel that keeps it — counts (active / invited / failed /
invitable), the **Send invitations** button, an invitation column on the
table, and per-row **Resend** on failed rows. The CSV export carries the
`invited_at` / `invitation_status` columns.

- The send **refuses while the site is coming_soon** — the invitation
  links people to the register and course pages, which 404 until open.
  The flip itself never sends; pressing this button is a deliberate,
  separate step (step 10 of Opening day below).
- The run is sequential with a per-row status commit, so a crash loses
  nothing already recorded, and **re-running is the retry**: sent rows
  are always skipped, so a second press after a partial failure reaches
  only the failed rows. There is no automatic retry, as with 019.
- Removed entries are never invited, including entries removed after a
  failed attempt. Each send is logged in `email_message` (kind
  `invitation`); the run summary goes to the app log.
- The email names the course and links its page; it carries no course
  facts, no Registry mention, and closes by saying superCPE will not
  email them again. That closing line is load-bearing: there is no
  second email, ever, and no unsubscribe machinery because there is no
  subscription.

## Google sign-in (030)

Participants may sign in, or create a participant account, with a
Google account. ID-token flow: the browser renders Google's button
(Google Identity Services), Google hands it a signed ID token, the
browser POSTs the token to `/api/v1/auth/google`, and the API verifies
the signature against Google's published keys, the issuer, the audience
(our client id), and the expiry. There is **no client secret, no
redirect URI, no callback route**, and nothing Google issues is stored.
One config value: `GOOGLE_CLIENT_ID`. It is optional and alone — not
part of the open gate; unset means the button does not render and the
endpoint refuses. Preflight prints a "configured / not configured" note
either way and never refuses over it.

Google is an identity, not a role: only participant accounts sign in
with it. Admin and reviewer accounts are refused with the same generic
answer as a bad token, so an operator's Google account being
compromised is not an admin compromise.

To set it up:

1. In Google Cloud Console, create (or pick) a project named for
   superCPE, then **APIs & Services → Credentials → Create credentials
   → OAuth client ID**, application type **Web application**, name it
   `superCPE web`.
   - **Authorized JavaScript origins**: `https://supercpe.com` and the
     local dev origin (`http://localhost:5173`).
   - **Authorized redirect URIs**: **none**. The ID-token flow uses no
     redirect; leave the list empty.
   - Copy the client id (`…apps.googleusercontent.com`). The client
     secret Google also shows is not used anywhere; do not copy it into
     any env.
2. Set `GOOGLE_CLIENT_ID=<the id>` in `/srv/supercpe/.env` (locally,
   `backend/.env`) and deploy. Preflight prints `note: GOOGLE_CLIENT_ID
   is configured`. Nothing in the Caddyfile needs a header change: no
   Content-Security-Policy, Cross-Origin-Opener-Policy, or frame header
   is set today (only HSTS), so Google's script, popup, and iframe are
   not blocked. Should a CSP ever be added, it must allow
   `https://accounts.google.com/gsi/client` in `script-src`,
   `https://accounts.google.com/gsi/` in `frame-src` and `connect-src`,
   `https://accounts.google.com/gsi/style` in `style-src`, and a COOP of
   `same-origin-allow-popups` if COOP is set. The login rate limit
   (`zone login`) covers `/api/v1/auth/google` too.
3. **The consent screen** (APIs & Services → OAuth consent screen /
   Google Auth Platform → Branding): user type **External**; app name
   `superCPE`; a support email; and a **privacy policy URL**.
   **superCPE has no privacy policy page.** `/policies` holds the 8.01
   CPE policies (registration, refund, complaint), which are not a
   privacy policy, and must not be handed to Google as one. Until the
   operator decides where a privacy policy lives (a new page, a hosted
   document — its own small feature), leave the OAuth app in **Testing**
   publishing status: sign-in then works only for the Google accounts
   listed under **Test users** (add your own), which is enough for the
   acceptance walkthrough and for staff. Moving to **In production**
   (any Google account may sign in) requires the privacy policy URL and,
   because the app requests only the basic `openid email profile`
   scopes, no Google verification review.
4. Walk it: on `/login` at open, sign in with Google as a new address
   (a Test user while in Testing) — lands on `/my/courses`, `/account`
   says "Sign-in methods: Google"; then register a password account and
   sign in with Google using the same address — same account, `/account`
   says "Password and Google". A Google-only account gets a password
   only through a reset flow, which does not exist yet (ROADMAP 017a);
   until it does, such an account signs in with Google only.

Turning it off is unsetting `GOOGLE_CLIENT_ID` and deploying: the
button disappears and the endpoint refuses; linked accounts keep their
`google_sub` and sign in with their password if they have one.

## Opening day (021)

The ordered checklist for the flip. Each step's full procedure lives in
its own section; this list only sequences them.

1. **014 complete**: the course ingested on production, the real
   reviewer's sign-off recorded, and the course published — priced,
   fully disclosing (see Re-ingest a course, and the admin course page's
   readiness panel).
2. **Policies published (011)**: registration, refund, and complaint
   policies each have a current version.
3. **Email proven (017)**: SMTP configured, SPF/DKIM in place, and the
   admin test-send delivered — see Outbound email (017).
4. **Stripe live keys (018/026)**: the transport — DNS, TLS, Caddy,
   signature verification, the handler itself — was proven in advance
   by the production verification run in Payments (018), on sandbox
   keys, while still coming-soon; check its log has a dated pass. Before
   the swap, three things that exist only in the sandbox today
   (2026-09-12) must be created in live mode:
   - **A live restricted key.** The sandbox runs on the standard
     `sk_test_…` key; live must never run on the standard key. Create a
     live restricted key with the union of the 018 and 029 scopes —
     Checkout Sessions write, Customers write, Subscriptions read,
     Coupons write, Billing Portal write, Invoices read, Products and
     Prices read, Charges read, Webhook Endpoints read — and use it as
     `STRIPE_SECRET_KEY` on production.
   - **A live Product and yearly Price** ("superCPE annual
     subscription", USD 149.00/year — Subscriptions (029) step 1) and a
     new `STRIPE_SUBSCRIPTION_PRICE_ID` for it. The sandbox id
     `price_1UEtb2GWw04RDXCnRbBgU2KL` is mode-specific: the open gate
     checks presence and preflight checks the amount, neither checks
     the mode, so leaving it in place fails only on the first live
     subscribe.
   - **The four 029 events on the live webhook destination**
     (`customer.subscription.updated`, `customer.subscription.deleted`,
     `invoice.paid`, `invoice.payment_failed`); the sandbox destination
     already has all seven.

   Then the key swap: all four `STRIPE_*` values to live in **one
   edit** (the live restricted key; the live endpoint's signing secret,
   not the sandbox one; the live Price id, not the sandbox one — 029),
   deploy, and a look at the sandbox endpoint's status for the disabled
   warning. Step 9 is the one live smoke purchase. Preflight and the
   open gate both refuse test keys, so a missed swap is a refused flip,
   not a silent one.
5. **Jurisdiction rows verified (020, optional)**: as far as intended —
   see Jurisdiction policies (020); the table showing nothing is a valid
   launch state.
6. **Google sign-in (030, optional)**: the site opens without it; if it
   is to be offered on opening day, both of these are done before the
   flip — see Google sign-in (030):
   - `GOOGLE_CLIENT_ID` set on production (OAuth Web application
     client, origins `https://supercpe.com`, no redirect URIs), deployed,
     and steps 1–2 of the acceptance walkthrough repeated on production
     with your own Google account listed as a Test user.
   - **Privacy policy decided.** The OAuth consent screen cannot leave
     Testing mode without a privacy policy URL, and `/policies` (the
     8.01 CPE policies) is not one. In Testing mode only listed Test
     users can sign in with Google — acceptable for launch, but the
     public button then fails for everyone else, so either publish a
     privacy policy and move the app to In production, or leave
     `GOOGLE_CLIENT_ID` unset until then.
7. **`launch_findings` empty**: the gate on `/admin/sponsor` agrees the
   site can open — no block-level findings.
8. **The flip**: set site mode to `open` (logged, with a note). This
   closes the waiting list permanently.
9. **Smoke test**: register a real account, buy the course in live mode
   — the one live purchase; everything else was proven on sandbox keys
   — confirm the enrollment appears and the row on `/admin/payments`
   carries no Test marker; refund yourself per the refund runbook in
   Payments (018) if desired.
10. **Then** press **Send invitations** on `/admin/waiting-list` — only
    after the smoke test proved the pages the email links to.
11. **Watch the failed column**: per-row Resend (or a second press of
    the batch button) as needed — see Waiting-list invitations (021).

## Site identity (022)

The favicon.ico, app icons, OG link-preview image, and web manifest are
all generated by one committed script from three sources: the icon in
`frontend/public/favicon.svg`, the words in `frontend/site.config.json`,
and the colors in `frontend/src/styles/global.css`. After any change to
those — a new icon, new palette, new name — regenerate and rebuild:

    backend/.venv/bin/python frontend/scripts/generate_identity.py
    cd frontend && npm run build

(The script runs on the backend venv's Python because Pillow ships with
it, rasterizes the SVG with macOS `sips`, and draws the OG wordmark with
the certificate DejaVu fonts already in the repo. Nothing else in the
app references the generated files except by filename.)

**The icon is favicon-only (024).** `favicon.svg` is a Flaticon-licensed
graphic; the license permits favicon use and forbids use as a logo or
trademark. It goes in the browser tab, the apple-touch icon, and the
manifest icons, and nowhere else — not in a header, a page body, the OG
card, a certificate, or an email. The OG card is the wordmark alone.
When the browser keeps showing an old icon, bump the `?v=` query on the
three icon links in `frontend/index.html`.

Two cache facts to know:

- **Link-preview caches are sticky.** iMessage, Slack, LinkedIn, and X
  cache the OG card per URL on their own schedule. After a deploy that
  changes `og.png` or the tags, old previews persist for hours or days;
  the only levers are time, each platform's debugger where one exists,
  or appending a throwaway query string (`?v=2`) when testing — a query
  string is a different URL to a scraper.
- **Favicons cache hard too.** The SVG favicon is content-hashed by the
  build, so a rebrand busts it; `favicon.ico`, `apple-touch-icon.png`,
  and `og.png` keep fixed names (old browsers and scrapers fetch them
  blindly), so after a rebrand those change in place and simply take
  time.

`/sitemap.xml` is answered by the API (mode-aware: only the root while
coming_soon, the full public set at open) through a rewrite in the
Caddyfile, so shipping 022 needs the routine deploy plus a Caddy
reload. `robots.txt` is a static file in `frontend/public/` and welcomes
indexing — the coming-soon page being indexed before opening day is the
point.

## When /health goes red

The monitor alerts on non-200. Fields, in the order to check:

- `database: error` — the API cannot reach the managed cluster. Check
  the cluster's status page in the control panel, then the trusted-source
  list (a rebuilt droplet has a new IP), then `DATABASE_URL` in
  `/srv/supercpe/.env`. The driver error is in the api container's log:
  `docker logs --tail=50 $(docker ps -q --filter label=com.docker.compose.service=api)`
  — `docker compose logs api` will not do here, because the compose file
  requires `GIT_SHA` and a shell outside `deploy.sh` has not exported it
  (see the note under Layout; the `docker logs` form needs no prefix).
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

## Pre-launch reset

Until Opening day step 0, production holds test data — nothing in the
database is a 9.02 record, and resetting it is a routine testing step.
The exception is the waiting list (015): public signups are real people
owed one invitation (021), so the reset carries their rows across.

    ssh -t deploy@138.197.35.128 /srv/supercpe/repo/deploy/reset-db.sh

It refuses unless `/api/v1/site` reports `coming_soon`, saves the
waiting-list rows to a timestamped file, drops and recreates the
`public` schema (not the database — see first-deploy step 6 on
ownership), migrates to head, restores the waiting-list rows, starts
the api, checks `/health`, and prompts for a new admin.

After a reset: `site_mode` is `coming_soon`, the sponsor profile is
blank (fill `/admin/sponsor` before any certificate), and packages must
be re-uploaded (Re-ingest a course). Spaces is untouched — test objects
under `packages/`, `certificates/`, and `audits/` remain. Resets end at
Opening day step 0.
