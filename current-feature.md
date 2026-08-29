# 012 — Spaces storage, production config, and deployment to superCPE.com

## Goal

Put superCPE on supercpe.com in `coming_soon` mode with a fresh, empty
production database, durable object storage, automated backups, and a
written operations runbook — so that Phase B can start and the records
Section 9 requires the sponsor to keep for five years are kept somewhere
that survives a lost laptop or a dead droplet.

This feature builds no product behavior. It changes where the existing
behavior runs and adds what running it responsibly requires: a second
`Storage` implementation, presigned video delivery, a health endpoint
that tells the truth, and deploy/rollback/restore procedures that have
each been exercised once before the feature is called done.

## In scope

- `SpacesStorage`: the second implementation of the 002 `Storage`
  protocol, plus presigned GET URLs for video; the `/media/` route
  becomes local-only.
- Production settings: environment-driven, `dev` off, secure cookies,
  same-origin CORS, secrets outside the repo.
- Containerized runtime (API + reverse proxy with automatic TLS),
  managed Postgres, deploy and rollback scripts, migrations on deploy.
- Backups: managed-database daily snapshots plus a nightly logical dump
  to Spaces under `backups/`; a restore drill.
- `/api/v1/health` reporting version, database, storage, and ffprobe
  status; an external uptime check.
- Login rate limiting at the proxy (009's known gap).
- `docs/OPERATIONS.md`: deploy, rollback, restore, rotate a secret, create
  the first admin, re-ingest a course.
- First deployment, with the site in `coming_soon` and nothing public but
  009's placeholder and `/api/v1/site`.

## Out of scope

- The landing page and waiting list (013), tester accounts (014).
- Any product code change not required to run in production. If a bug
  surfaces during deployment, fix it as its own changelog entry, not
  inside this one.
- Copying the development database to production. Production starts
  empty. The dev database's fictitious reviewer, test participant, and
  test policies never leave the laptop; ASC842-PCX is re-ingested from
  the four exported zips and reviewed for real when the second CPA
  exists.
- CDN, multi-region, autoscaling, Kubernetes.
- Email of any kind (016/018/020).

## Locators — read these before writing code

- **9.02** — retain adequate documentation for a minimum of five years.
  This is the paragraph that makes backups and durable storage a
  compliance matter, not just an engineering one: a record that exists
  only on one disk is not retained.
- **4.05.2** — facilities and technology "carefully monitored." The
  health endpoint and uptime check are the monitoring.
- **9.01** — certificates delivered and retrievable; the `certificates/`
  prefix must survive.
- **9.02.2(7)** — program materials retained; the `packages/` prefix.

## Human tasks before Claude Code starts

These need your DigitalOcean account and DNS, not code. Do them first so
the build can be tested against real endpoints.

1. Create a Spaces bucket (private, region of your choice — NYC3 is
   nearest), and an access key scoped to it. Note the bucket name,
   region, and endpoint.
2. Create a managed Postgres 16 cluster (smallest size is fine), with a
   `supercpe` database and a `supercpe` user; enable daily backups (on
   by default). Note the connection string with `sslmode=require`.
3. Create a droplet (Ubuntu 24.04, 2 GB is enough for Phase B) in the
   same region; add your SSH key; note its IP.
4. Point `supercpe.com` and `www.supercpe.com` A records at the droplet.
5. Set up an external uptime monitor (DigitalOcean's own, UptimeRobot,
   or similar) on `https://supercpe.com/api/v1/health` — do this after
   the first deploy.

Give Claude Code the bucket name, region, endpoint, database host, and
droplet IP. Never give it the keys or passwords; they go into the
server's `.env` by your hand (the runbook says where).

## Data model

No migration. No model changes. `audit_exports.storage_key`,
`completions.certificate_key`, and package video keys are already
storage-relative; they work unchanged under the new implementation.

## Tasks

1. **`SpacesStorage`** in `app/services/storage.py` alongside
   `LocalStorage`: `put`, `open`, `exists`, `delete`, and a new protocol
   method `url_for(key, expires_seconds)`. Spaces is S3-compatible; use
   `boto3` against the Spaces endpoint. `LocalStorage.url_for` returns the
   existing `/media/` path. Selected by `STORAGE_BACKEND` (`local` |
   `spaces`); refuse to boot on `spaces` with any of `SPACES_BUCKET`,
   `SPACES_REGION`, `SPACES_ENDPOINT`, `SPACES_KEY`, `SPACES_SECRET`
   missing. Objects are written with `ContentType` set and no public
   ACL. Bucket is private; nothing is ever served directly.

2. **Video delivery.** The play endpoints (006 preview and 010
   enrollment) hand out `storage.url_for(key, VIDEO_URL_SECONDS)` —
   `VIDEO_URL_SECONDS = 3600` in `app/constants/storage.py`, ours — so a
   URL expires within an hour and cannot be shared usefully. Under
   `local`, that is the `/media/` path as today; under `spaces`, a
   presigned GET. The `/media/` route is mounted only when
   `STORAGE_BACKEND=local`. Certificate and audit downloads keep
   streaming through the API (they need the session check), reading from
   storage as today.

3. **Settings.** `app/config.py` gains `ENV` (`dev` | `prod`), and in
   `prod`: `dev` is false (Secure cookies), `CORS_ORIGINS` must be exactly
   `https://supercpe.com`, `DATABASE_URL` must carry `sslmode=require`,
   `STORAGE_BACKEND` must be `spaces`, and `SECRET_KEY`-class values must
   be present and at least 32 bytes. Boot refuses with every violation
   listed, in the 002 style. `.env.example` documents every variable
   with a one-line meaning; `.env` is gitignored (verify).

4. **Runtime.** `deploy/` at the repo root:
   - `Dockerfile` for the API: Python 3.12 slim, `ffmpeg` installed
     (ffprobe is a boot requirement from 002), non-root user, `alembic
     upgrade head` as a separate entrypoint command, uvicorn with a
     fixed worker count.
   - `Dockerfile.web` building the Vite frontend to static files.
   - `Caddyfile`: TLS for supercpe.com (automatic via Let's Encrypt),
     `www` → apex redirect, static frontend, `/api/*` proxied to the API,
     `/media/*` absent in prod, HSTS, and a rate limit on
     `POST /api/v1/auth/login` (10/minute per IP) — Caddy's rate-limit
     plugin, or nginx if that plugin proves awkward; justify the choice.
   - `docker-compose.yml`: `caddy` and `api` services; Postgres is the
     managed cluster, not a container; `.env` mounted read-only.
   - `deploy.sh` (run on the droplet): `git fetch`, check out the
     requested tag or sha, build, run migrations, restart, verify
     `/api/v1/health` reports the new version, and print it. Keeps the
     previous image tagged so `rollback.sh <sha>` is a checkout, a
     rebuild from cache, and a restart — with the explicit note that
     rollback does not undo a migration, and which migrations since 001
     are reversible.
   - `backup.sh` and a cron entry: nightly `pg_dump` (custom format) of
     the managed database, gzip, upload to `backups/<date>.dump.gz`,
     delete local copy, keep the last 90 in Spaces and one per month
     beyond that; failure of the upload exits non-zero and is logged
     where the uptime monitor can see it (a `last_backup_at` in
     `/health`, task 5).

5. **Health.** `GET /api/v1/health` returns `{version, env, database:
   ok|error, storage: ok|error, ffprobe: ok|error, last_backup_at}` with
   HTTP 503 if any is `error`. `version` is the git sha baked at build
   time. Storage check is a HEAD on a known sentinel key written at first
   deploy (`health/sentinel`); database check is `SELECT 1`;
   `last_backup_at` is read from a `backups/LATEST` object the backup
   script writes. The endpoint stays ungated (009).

6. **Security posture, stated in one place.** `docs/OPERATIONS.md` opens
   with it: TLS only, HSTS, HttpOnly/Secure/SameSite=Lax session cookie,
   argon2id, login rate limit, private bucket with hour-lived presigned
   video, secrets in the server `.env` (mode 600, owned by the deploy
   user), managed Postgres reachable only from the droplet's private
   network with SSL required, no ports open but 22, 80, 443. Include what
   is deliberately *not* done yet: no WAF, no MFA, no intrusion detection.

7. **`docs/OPERATIONS.md` procedures**, each written as numbered steps
   that were actually executed once during this feature:
   - First deploy on a fresh droplet (packages, Docker, clone, `.env`,
     `deploy.sh`, sentinel, first admin via `python -m app.cli
     create-admin` inside the container).
   - Routine deploy of a tag.
   - Rollback.
   - Restore: from a managed snapshot, and from a `backups/` dump into
     a scratch database, then verifying `completions` and
     `certificates/` line up. This drill must be done for real against
     the empty production database before the feature ships, and the
     runbook records the date it was done and how long it took.
   - Rotate: Spaces key, database password, `SECRET_KEY` (and what a
     `SECRET_KEY` rotation does to sessions — everyone is signed out).
   - Re-ingest a course from its exported zips.
   - What to do when `/health` goes red, per field.

8. **Tests.** `SpacesStorage` against `moto`'s S3 mock (test-only
   dependency; justify): put/open/exists/delete round-trip, `url_for`
   returns a signed URL containing the key and an expiry, `put` never
   sets a public ACL. Config validation: every `prod` refusal fires with
   the offending variable named. `/health` returns 503 and names the
   failing component when storage is unreachable (mock). The `/media/`
   route is absent when `STORAGE_BACKEND=spaces`. All prior tests pass
   under `local`; the count goes up.

## COMPLIANCE.md rows

| 9.02 | (append) | 012 | Object storage on Spaces (private bucket; `packages/`, `certificates/`, `audits/` write-once); managed Postgres with daily snapshots; nightly logical dump to `backups/` with 90-day + monthly retention; restore drill recorded in `docs/OPERATIONS.md` | Spaces has no object versioning; write-once discipline is enforced by the application, not the bucket. Off-provider copy of backups is not implemented. |
| 4.05.2 | facilities and technology carefully monitored | 012 | `/api/v1/health` (db, storage, ffprobe, last backup) with 503 on failure; external uptime monitor on it | Monitoring is availability only; no load testing has been done. |
| 9.01 | (append) | 012 | Certificates persist in `certificates/` on Spaces and are covered by the backup policy | — |

## Acceptance

1. `https://supercpe.com` serves 009's coming-soon placeholder over TLS
   with a valid certificate; `http://` and `www` redirect; `/api/v1/site`
   reports `coming_soon`; `/api/v1/health` reports every component `ok`,
   the deployed sha, and a `last_backup_at` from the first manual run of
   `backup.sh`.
2. `/login` works; the first admin created on the server signs in; the
   session cookie is `Secure` and `HttpOnly` (check in the browser).
3. As admin: upload `ASC842-PCX-01.zip`; the object appears in the
   bucket under `packages/`; the preview player plays it via a presigned
   URL that stops working after an hour; `/media/` returns 404.
4. Create a draft course, attach the package, generate an audit bundle;
   it lands under `audits/` and downloads.
5. Run `rollback.sh` to the previous sha and back; `/health` shows each
   version in turn.
6. The restore drill in `docs/OPERATIONS.md` has a date on it.
7. `ADMIN_TOKEN`, keys, and passwords appear nowhere in the repo
   (`git grep` for each variable name's value pattern is empty; `.env`
   is ignored).
8. `pytest`: all pass; count exceeds 199.

## When done

- Changelog per CLAUDE.md, including: why managed Postgres over a
  container (backups are 9.02), why Caddy (or nginx), the `moto` and
  `boto3` justifications, the presigned-URL lifetime, and the note that
  production started from an empty database by design.
- COMPLIANCE.md rows above.
- ROADMAP: mark Phase A complete; add an improvement note for
  off-provider backup copies (a second bucket at a different provider,
  or a periodic download), which 9.02 arguably wants and this feature
  does not do.
- Record in `docs/OPERATIONS.md` the four things that live only in your
  head today: the DigitalOcean account owner, where the `.env` values
  came from, the domain registrar, and the uptime monitor login — so the
  next person (or you, in a year) can run the site.
