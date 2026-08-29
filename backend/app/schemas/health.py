from typing import Literal

from pydantic import BaseModel

Check = Literal["ok", "error"]


class HealthResponse(BaseModel):
    version: str
    env: str
    database: Check
    storage: Check
    ffprobe: Check
    # UTC timestamp of the newest successful backup upload, or null before
    # the first one. Staleness here is the backup-failure alarm (the
    # uptime monitor watches this endpoint), so it never flips the status
    # code by itself.
    last_backup_at: str | None
