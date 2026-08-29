#!/usr/bin/env bash
# Deploy a tag or sha on the droplet:
#
#     /srv/supercpe/repo/deploy/deploy.sh v012
#
# Checks out the ref, builds images tagged with its sha (the previous
# deploy's images stay on disk, so rollback.sh is a rebuild from cache),
# runs migrations as a one-off container, restarts, and refuses to call
# the deploy done until /api/v1/health reports the new sha.
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

echo "Running migrations ..."
# A failed migration stops here, before the old API is touched. Note:
# rollback.sh does NOT undo migrations — see docs/OPERATIONS.md.
$COMPOSE run --rm api alembic upgrade head

echo "Restarting ..."
$COMPOSE up -d

echo "Waiting for $HEALTH_URL to report $GIT_SHA ..."
for _ in $(seq 1 30); do
    BODY=$(curl -fsS "$HEALTH_URL" 2>/dev/null || true)
    if [ -n "$BODY" ] && echo "$BODY" | grep -q "\"version\":\"$GIT_SHA\""; then
        echo "Deployed $GIT_SHA"
        echo "$BODY"
        exit 0
    fi
    sleep 2
done

echo "Health never reported $GIT_SHA — the old version may still be running:" >&2
curl -fsS "$HEALTH_URL" >&2 || true
exit 1
