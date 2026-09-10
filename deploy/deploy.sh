#!/usr/bin/env bash
# Deploy a tag or sha on the droplet:
#
#     /srv/supercpe/repo/deploy/deploy.sh v012
#
# Checks out the ref, builds images tagged with its sha (the previous
# deploy's images stay on disk, so rollback.sh is a rebuild from cache),
# runs migrations as a one-off container, restarts, and refuses to call
# the deploy done until /api/v1/health reports the new sha *and* a 2xx
# (wait-for-health.sh tells "new version unhealthy" from "old version
# still running").
set -euo pipefail

REF="${1:?usage: deploy.sh <tag-or-sha>}"
REPO=/srv/supercpe/repo
COMPOSE="docker compose -f deploy/docker-compose.yml"
HEALTH_URL="https://supercpe.com/api/v1/health"

cd "$REPO"
git fetch --all --tags --prune
git checkout --detach "$REF"
GIT_SHA=$(git rev-parse HEAD)
export GIT_SHA

echo "Building $GIT_SHA ..."
$COMPOSE build

echo "Running preflight ..."
# Every check that would refuse boot in prod (config validations, bucket
# versioning), run from the newly built image against the production env
# file. A failure stops here, before migrations, with the old version
# still serving — a preflight abort is a failed deploy, not an outage.
$COMPOSE run --rm api python -m app.cli preflight

echo "Running migrations ..."
# A failed migration stops here, before the old API is touched. Note:
# rollback.sh does NOT undo migrations — see docs/OPERATIONS.md.
$COMPOSE run --rm api alembic upgrade head

echo "Restarting ..."
$COMPOSE up -d

echo "Waiting for $HEALTH_URL to report $GIT_SHA ..."
# Three outcomes, distinguished by wait-for-health.sh (023c D4): healthy
# new version (0), new version running but unhealthy (1, with the failing
# components named — read `docker compose -f deploy/docker-compose.yml
# logs api` for the storage line), or the sha never seen (2, the old
# version may still be running).
exec "$REPO/deploy/wait-for-health.sh" "$GIT_SHA" "$HEALTH_URL" 30 2
