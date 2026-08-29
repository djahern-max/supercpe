"""The truth-telling health endpoint (4.05.2: the technologies employed
in delivery are "carefully monitored" — this is what the external uptime
monitor watches). Ungated: it carries no participant data and must be
readable while the site is coming_soon.
"""

import io
import shutil

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.storage import BACKUP_LATEST_KEY, HEALTH_SENTINEL_KEY
from app.db import get_db
from app.schemas.health import HealthResponse
from app.storage import LocalStorage, Storage, get_storage

router = APIRouter()


def _database_check(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _storage_check(storage: Storage) -> str:
    """A read of the sentinel written at first deploy proves the bucket,
    credentials, and network all work. LocalStorage writes its own
    sentinel on first ask: a writable disk is what health means there."""
    try:
        if storage.exists(HEALTH_SENTINEL_KEY):
            return "ok"
        if isinstance(storage, LocalStorage):
            storage.put(HEALTH_SENTINEL_KEY, io.BytesIO(b"ok"))
            return "ok"
        return "error"
    except Exception:
        return "error"


def _last_backup_at(storage: Storage) -> str | None:
    """First line of backups/LATEST, written by the backup upload; absent
    until the first backup succeeds."""
    try:
        with storage.open(BACKUP_LATEST_KEY) as latest:
            return latest.read().decode("utf-8").splitlines()[0]
    except Exception:
        return None


@router.get("/health", response_model=HealthResponse)
def health(
    db: Session = Depends(get_db), storage: Storage = Depends(get_storage)
):
    body = {
        "version": settings.app_version,
        "env": settings.env,
        "database": _database_check(db),
        "storage": _storage_check(storage),
        "ffprobe": "ok" if shutil.which("ffprobe") else "error",
        "last_backup_at": _last_backup_at(storage),
    }
    if "error" in (body["database"], body["storage"], body["ffprobe"]):
        return JSONResponse(status_code=503, content=body)
    return body
