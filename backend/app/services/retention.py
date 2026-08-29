"""The 9.02 retention date, derived and stated, never enforced.

`retain_until` exists so the admin completions table and the audit bundle
can state until when each record must be kept. Nothing deletes at the
boundary: retention is a floor and superCPE keeps everything.
"""

from datetime import datetime

from app.constants.retention import RETENTION_YEARS


def retain_until(completed_at: datetime) -> datetime:
    """Exactly RETENTION_YEARS after the completion date. A Feb 29
    completion retains until Mar 1 — the day after the nonexistent
    anniversary, never before it."""
    try:
        return completed_at.replace(year=completed_at.year + RETENTION_YEARS)
    except ValueError:
        return completed_at.replace(
            year=completed_at.year + RETENTION_YEARS, month=3, day=1
        )
