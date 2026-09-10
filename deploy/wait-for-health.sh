#!/usr/bin/env bash
# Wait for the health endpoint to report a sha, and say what it found:
#
#     deploy/wait-for-health.sh <sha> <health-url> [attempts] [sleep-seconds]
#
# Three outcomes (023c D4 — the old loop treated any non-2xx as "the old
# version may still be running", including a 503 that already carried the
# new sha):
#
#   exit 0  the new version is running and healthy (2xx with the sha)
#   exit 1  the new version is running but unhealthy: the body carries the
#           sha and a non-2xx status; the components reporting "error" are
#           named
#   exit 2  health never reported the sha: the old version may still be
#           running
#
# Polls for the whole window in every case — a component can still be
# coming up — and classifies by the last body seen. Needs only curl and
# grep, so it runs on the droplet as-is.
set -uo pipefail

SHA="${1:?usage: wait-for-health.sh <sha> <health-url> [attempts] [sleep-seconds]}"
URL="${2:?usage: wait-for-health.sh <sha> <health-url> [attempts] [sleep-seconds]}"
ATTEMPTS="${3:-30}"
SLEEP="${4:-2}"

BODY_FILE=$(mktemp)
trap 'rm -f "$BODY_FILE"' EXIT

LAST_STATUS=""
LAST_BODY=""
SEEN_SHA=0

for _ in $(seq 1 "$ATTEMPTS"); do
    STATUS=$(curl -sS -o "$BODY_FILE" -w '%{http_code}' "$URL" 2>/dev/null || echo "000")
    BODY=$(cat "$BODY_FILE" 2>/dev/null || true)
    LAST_STATUS="$STATUS"
    LAST_BODY="$BODY"
    if echo "$BODY" | grep -q "\"version\": *\"$SHA\""; then
        SEEN_SHA=1
        case "$STATUS" in
            2*)
                echo "Deployed $SHA"
                echo "$BODY"
                exit 0
                ;;
        esac
    fi
    sleep "$SLEEP"
done

if [ "$SEEN_SHA" = "1" ]; then
    # "database", "storage", "ffprobe", "bucket_versioning" — whichever
    # the body flags. The names come from the body itself, not a list
    # kept here, so a component added to /health is reported unchanged.
    FAILING=$(echo "$LAST_BODY" | grep -o '"[a-z_]*": *"error"' | sed 's/"\([a-z_]*\)".*/\1/' | tr '\n' ' ' | sed 's/ $//')
    echo "New version $SHA running, unhealthy (HTTP $LAST_STATUS): ${FAILING:-unknown component}" >&2
    echo "$LAST_BODY" >&2
    exit 1
fi

echo "Health never reported $SHA — the old version may still be running (last HTTP $LAST_STATUS):" >&2
echo "$LAST_BODY" >&2
exit 2
