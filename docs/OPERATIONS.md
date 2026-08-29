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

- DigitalOcean account owner: Daniel Ahern (danielaherniv@gmail.com) —
  confirm/correct.
- Where the `.env` values came from: `DATABASE_URL` from the managed
  Postgres cluster's connection details panel; `SPACES_KEY`/`SPACES_SECRET`
  from API → Spaces Keys; the rest per `deploy/env.production.example`.
- Domain registrar for supercpe.com: ____ (fill in).
- Uptime monitor and its login: ____ (fill in after the first deploy).

## Layout on the droplet

    /srv/supercpe/.env         secrets (mode 600, deploy user)
    /srv/supercpe/repo         git clone of this repository
    /srv/supercpe/backups      scratch space for nightly dumps (emptied nightly)
    /srv/supercpe/backup.log   backup.sh output, via cron

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
   exist.
7. `/srv/supercpe/repo/deploy/deploy.sh main` — builds, migrates the
   empty database to head, starts Caddy and the API, waits for
   `https://supercpe.com/api/v1/health` to report the deployed sha.
8. Write the storage sentinel the health check reads:
   `docker compose -f deploy/docker-compose.yml run --rm api python -m app.cli write-sentinel`
9. Create the first admin (password prompted, never a flag):
   `docker compose -f deploy/docker-compose.yml run --rm api python -m app.cli create-admin --email <you>`
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
3. `docker compose -f deploy/docker-compose.yml up -d --force-recreate api`
4. Check `/api/v1/health` and spot-check `completions` against
   `certificates/` (below).

**From a nightly dump in `backups/`** (into a scratch database first —
never straight over production):

1. List what exists: `docker compose -f deploy/docker-compose.yml run
   --rm api python -c "from app.storage import get_storage; from
   app.services.backups import dump_dates; print(sorted(dump_dates(get_storage())))"`
2. Download the chosen dump to the droplet:
   `docker compose -f deploy/docker-compose.yml run --rm -v /srv/supercpe/backups:/backups api python -c "import shutil; from app.storage import get_storage; s=get_storage(); shutil.copyfileobj(s.open('backups/<DATE>.dump.gz'), open('/backups/restore.dump.gz','wb'))"`
3. Create a scratch database on the cluster (control panel or `createdb`),
   then:
   `gunzip -c /srv/supercpe/backups/restore.dump.gz | docker run --rm -i postgres:16 pg_restore --no-owner -d "<postgresql://...scratch db url>"`
4. Verify the restore lines up with the bucket: every
   `completions.certificate_key` in the scratch database should exist
   under `certificates/` in Spaces
   (`SELECT certificate_key FROM completions WHERE certificate_key IS NOT NULL`
   against `storage.exists(...)`).
5. Only after that verification, either point `DATABASE_URL` at the
   scratch database or `pg_restore` into the real one.

**Restore drill record** (required by 012 before launch; repeat yearly):

| Date | Source | Time taken | Verified by |
|------|--------|-----------|-------------|
| _not yet performed — run the dump-restore drill against the empty production database and record it here_ | | | |

## Rotate a secret

**Spaces key:** DigitalOcean → API → Spaces Keys → create a new key
scoped to the bucket; put it in `/srv/supercpe/.env`; `docker compose -f
deploy/docker-compose.yml up -d --force-recreate api`; confirm `/health`
storage is `ok`; delete the old key. Presigned URLs signed by the old key
die with it — an hour's worth of play URLs at most.

**Database password:** control panel → cluster → Users → reset password;
update `DATABASE_URL` in `/srv/supercpe/.env`; recreate the api container
as above; confirm `/health` database is `ok`.

**Session secret:** there is none to rotate — sessions are server-side
random tokens (009). The equivalent gesture is revoking every session:
`docker compose -f deploy/docker-compose.yml run --rm api python -c
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

## When /health goes red

The monitor alerts on non-200. Fields, in the order to check:

- `database: error` — the API cannot reach the managed cluster. Check
  the cluster's status page in the control panel, then the trusted-source
  list (a rebuilt droplet has a new IP), then `DATABASE_URL` in
  `/srv/supercpe/.env`. `docker compose logs api` shows the driver error.
- `storage: error` — the sentinel HEAD failed: Spaces outage, deleted or
  rotated key, or someone deleted `health/sentinel`. Re-run
  `python -m app.cli write-sentinel` (inside the api container) after
  fixing credentials; if the sentinel object itself was the casualty,
  that command is the whole fix.
- `ffprobe: error` — the image is broken (ffmpeg is installed by the
  Dockerfile); a deploy with a modified Dockerfile is the likely cause.
  Roll back.
- `last_backup_at` stale (not a 503 by itself) — the nightly backup
  failed. `tail /srv/supercpe/backup.log`; run
  `/srv/supercpe/repo/deploy/backup.sh` by hand and watch it.
- Whole endpoint unreachable — Caddy or the droplet. `docker compose -f
  deploy/docker-compose.yml ps`, then `logs caddy`; then the droplet
  console in the control panel.
