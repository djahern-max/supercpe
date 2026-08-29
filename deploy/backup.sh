#!/usr/bin/env bash
# Nightly logical dump of the managed database to Spaces (9.02: retained
# records must survive the droplet). Cron entry (root or the deploy
# user), documented in docs/OPERATIONS.md:
#
#     15 3 * * * /srv/supercpe/repo/deploy/backup.sh >> /srv/supercpe/backup.log 2>&1
#
# Any failure exits non-zero and leaves backups/LATEST unstamped, so
# /api/v1/health's last_backup_at goes stale — that staleness is the
# alarm the uptime monitor sees. Retention (last 90 dumps, then one per
# month) is pruned by `app.cli upload-backup` inside the api container.
set -euo pipefail

REPO=/srv/supercpe/repo
ENV_FILE=/srv/supercpe/.env
BACKUP_DIR=/srv/supercpe/backups
STAMP=$(date -u +%F)
FILE="$BACKUP_DIR/$STAMP.dump.gz"

mkdir -p "$BACKUP_DIR"
cd "$REPO"

# pg_dump wants a plain postgresql:// URL; .env holds the SQLAlchemy one.
DATABASE_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
PG_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

echo "[$(date -u +%FT%TZ)] dumping to $FILE"
# postgres:16 matches the managed cluster's major version; custom format
# so restore can be selective.
docker run --rm postgres:16 pg_dump --format=custom --no-owner "$PG_URL" \
    | gzip > "$FILE"

echo "[$(date -u +%FT%TZ)] uploading"
docker compose -f deploy/docker-compose.yml run --rm \
    -v "$BACKUP_DIR:/backups:ro" \
    api python -m app.cli upload-backup "/backups/$STAMP.dump.gz"

rm -f "$FILE"
echo "[$(date -u +%FT%TZ)] done"
