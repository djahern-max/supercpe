from typing import Literal

from pydantic import BaseModel

Check = Literal["ok", "error"]


class HealthResponse(BaseModel):
    version: str
    env: str
    database: Check
    storage: Check
    ffprobe: Check
    # Object versioning on the bucket (013): "error" the moment it is not
    # Enabled, and it contributes to the 503 like the other components.
    # LocalStorage reports "ok" — there is nothing to version on a
    # developer disk.
    bucket_versioning: Check
    # UTC timestamp of the newest successful backup upload, or null before
    # the first one. Staleness here is the backup-failure alarm (the
    # uptime monitor watches this endpoint), so it never flips the status
    # code by itself.
    last_backup_at: str | None
    # UTC timestamp of the newest successful off-site mirror run, or null
    # while OFFSITE_* is unconfigured or no run has succeeded. Same rule
    # as last_backup_at: staleness (~26 hours for both) is the uptime
    # monitor's alarm, never a 503.
    last_offsite_backup_at: str | None
