"""Backup upload and retention against Spaces (9.02: documentation
retained for a minimum of five years cannot live on one disk).

`deploy/backup.sh` dumps the managed database on the droplet, then runs
`python -m app.cli upload-backup <file>` inside the api container, which
lands here: upload the dump under `backups/`, stamp `backups/LATEST` for
the health endpoint, and prune to the retention policy. Spaces-only by
design — backups exist to survive the machine, so a local "backup" would
be a lie.
"""

import io
import re
from datetime import date, datetime, timezone
from pathlib import Path

from app.constants.storage import (
    BACKUP_KEEP_RECENT,
    BACKUP_LATEST_KEY,
    BACKUPS_PREFIX,
)
from app.storage import SpacesStorage

# backups/2026-08-29.dump.gz
DUMP_KEY_RE = re.compile(
    re.escape(BACKUPS_PREFIX) + r"(\d{4}-\d{2}-\d{2})\.dump\.gz$"
)


def upload(storage: SpacesStorage, path: Path) -> str:
    """Uploads one dump, writes LATEST, prunes. Returns the key."""
    key = f"{BACKUPS_PREFIX}{path.name}"
    if not DUMP_KEY_RE.match(key):
        raise ValueError(
            f"backup file must be named <YYYY-MM-DD>.dump.gz, got {path.name}"
        )
    with open(path, "rb") as dump:
        storage.put(key, dump)
    stamp = datetime.now(timezone.utc).isoformat()
    storage.put(BACKUP_LATEST_KEY, io.BytesIO(f"{stamp}\n{key}\n".encode()))
    for stale in prunable_keys(dump_dates(storage)):
        storage.delete(f"{BACKUPS_PREFIX}{stale.isoformat()}.dump.gz")
    return key


def dump_dates(storage: SpacesStorage) -> list[date]:
    """Dates of every dump under backups/, from the object listing."""
    dates = []
    paginator = storage.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=storage.bucket, Prefix=BACKUPS_PREFIX):
        for obj in page.get("Contents", []):
            match = DUMP_KEY_RE.match(obj["Key"])
            if match:
                dates.append(date.fromisoformat(match.group(1)))
    return dates


def prunable_keys(dates: list[date]) -> list[date]:
    """Retention: the newest BACKUP_KEEP_RECENT dumps stay; beyond them,
    the earliest dump of each calendar month stays forever."""
    ordered = sorted(dates, reverse=True)
    recent = set(ordered[:BACKUP_KEEP_RECENT])
    older = sorted(d for d in ordered if d not in recent)
    monthly_keep = {}
    for day in older:
        monthly_keep.setdefault((day.year, day.month), day)
    keep = recent | set(monthly_keep.values())
    return [day for day in ordered if day not in keep]
