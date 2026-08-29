#!/usr/bin/env bash
# Roll back to a previously deployed sha:
#
#     /srv/supercpe/repo/deploy/rollback.sh <sha>
#
# A rollback is a deploy of an older ref: checkout, rebuild (from cache —
# the images are already on disk), restart, verify. What it does NOT do
# is undo a migration. Every migration in this repo has a downgrade, but
# every one of them drops the tables or columns its upgrade created —
# running one destroys retained records (9.02) — so `alembic downgrade`
# is never part of rollback. Migrations are written additive enough that
# the previous app version runs against the newer schema; if one ever is
# not, the fix is a new forward migration, not a downgrade.
set -euo pipefail

SHA="${1:?usage: rollback.sh <sha>}"
exec "$(dirname "$0")/deploy.sh" "$SHA"
