"""Storage and backup numbers. All of these are superCPE's own choices,
not NASBA's; they exist here so the deploy scripts, the health endpoint,
and the tests read the same values.

9.02 is why backups exist at all: the sponsor must retain adequate
documentation for a minimum of five years, and a record that exists only
on one disk is not retained.
"""

# How long a presigned video URL stays valid. Long enough to watch a
# lesson segment, short enough that a shared link dies within the hour.
VIDEO_URL_SECONDS = 3600

# Object the health endpoint HEADs to prove storage is reachable with the
# configured credentials. Written once at first deploy
# (`python -m app.cli write-sentinel`).
HEALTH_SENTINEL_KEY = "health/sentinel"

# Where nightly logical dumps land, as `backups/<YYYY-MM-DD>.dump.gz`.
BACKUPS_PREFIX = "backups/"

# Written by the backup upload after every successful dump: the UTC
# timestamp and key of the newest backup. `/api/v1/health` reads it, so a
# stale value is visible to the uptime monitor.
BACKUP_LATEST_KEY = "backups/LATEST"

# Retention: every dump from the last 90 days, and the first dump of each
# calendar month forever beyond that.
BACKUP_KEEP_RECENT = 90

# With bucket versioning on (013), a pruned or re-uploaded dump leaves a
# noncurrent version behind; the lifecycle rule set by
# `python -m app.cli bucket-setup` expires those under backups/ after
# this many days. A nightly dump overwritten by the same day's re-run has no
# retention value beyond a week, whereas every other prefix (packages/,
# certificates/, audits/) is 9.02 material and is never expired — the
# lifecycle configuration carries no rule for them at all.
BACKUP_NONCURRENT_DAYS = 7

# Written in the PRIMARY bucket by `app.cli mirror-offsite` after every
# successful off-site mirror run: the UTC timestamp of that run.
# `/api/v1/health` reads it as last_offsite_backup_at, so a dead off-site
# provider is visible to the uptime monitor without ever masking the
# primary backup's own staleness.
OFFSITE_STAMP_KEY = "backups/OFFSITE"

# What the off-site mirror copies besides the nightly dumps: the 9.02.2
# audit bundles and the 9.01 certificates. packages/ is deliberately not
# here — videos are large and every exported zip also exists on the
# machine that produced it (video-tool's dist/); recorded as a known gap.
MIRRORED_PREFIXES = ("certificates/", "audits/")
