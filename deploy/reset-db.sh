#!/usr/bin/env bash
# Pre-launch only: production holds test data.
set -euo pipefail
cd /srv/supercpe/repo
DC="docker compose -f deploy/docker-compose.yml"
set -a; . /srv/supercpe/.env; set +a
PSQL_URL=$(printf '%s' "$DATABASE_URL" | sed 's|^postgresql+[a-z0-9]*://|postgresql://|')

IMG=$($DC ps --format '{{.Image}}' api); export GIT_SHA=${IMG##*:}

$DC stop api
trap '$DC up -d api' EXIT
docker run --rm postgres:16 psql -v ON_ERROR_STOP=1 "$PSQL_URL" \
  -c 'DROP SCHEMA public CASCADE' -c 'CREATE SCHEMA public'
$DC run --rm api alembic upgrade head
$DC up -d api
trap - EXIT
sleep 5
curl -fsS https://supercpe.com/api/v1/health && echo " OK"