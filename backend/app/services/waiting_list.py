"""The coming-soon waiting list: who wants the course when it opens.

These are not CPE records (see the model docstring) — no participant, no
enrollment, no retention floor. Signup is idempotent: the same email a
second time returns the existing row and moves nothing; a signup against
a removed row clears the removal and re-adds with the fresh details,
keeping the original `created_at`. The honeypot never reaches this
module — the router answers it before calling `sign_up`.
"""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.jurisdictions import US_JURISDICTIONS
from app.models.waiting_list import WaitingListEntry


class WaitingListRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_by_email(db: Session, email: str) -> WaitingListEntry | None:
    return db.scalar(
        select(WaitingListEntry).where(
            WaitingListEntry.email == email.strip().lower()
        )
    )


def sign_up(
    db: Session, name: str, email: str, state: str, firm: str = ""
) -> WaitingListEntry:
    name = name.strip()
    email = email.strip().lower()
    state = state.strip().upper()
    firm_value = firm.strip() or None

    errors = []
    if not name:
        errors.append("name is blank")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        errors.append(f'"{email}" is not an email address')
    if state not in US_JURISDICTIONS:
        errors.append(
            f'"{state}" is not a two-letter US licensing jurisdiction code'
        )
    if errors:
        raise WaitingListRuleViolation(errors)

    existing = get_by_email(db, email)
    if existing is None:
        entry = WaitingListEntry(name=name, email=email, state=state, firm=firm_value)
        db.add(entry)
        db.commit()
        return entry
    if existing.removed_at is not None:
        # Re-add: the removal is cleared and the details refreshed, but
        # created_at stays — the row records when they first signed up.
        existing.removed_at = None
        existing.removed_reason = None
        existing.name = name
        existing.state = state
        existing.firm = firm_value
        db.commit()
    return existing


def active_entries(db: Session) -> list[WaitingListEntry]:
    """Everyone still on the list, oldest signup first. Removed rows are
    excluded from every count, listing, and export — this is the only
    listing query, so they cannot leak into one."""
    return list(
        db.scalars(
            select(WaitingListEntry)
            .where(WaitingListEntry.removed_at.is_(None))
            .order_by(WaitingListEntry.created_at.asc(), WaitingListEntry.id.asc())
        )
    )


def remove(
    db: Session, entry_id: int, reason: str = ""
) -> WaitingListEntry | None:
    """Soft delete; idempotent. None when no such row exists."""
    entry = db.get(WaitingListEntry, entry_id)
    if entry is None:
        return None
    if entry.removed_at is None:
        entry.removed_at = _now()
        entry.removed_reason = reason.strip() or None
        db.commit()
    return entry


def export_csv(db: Session) -> bytes:
    """The active list as UTF-8 CSV with ISO-8601 timestamps — the file
    021's invitations will be fed from."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["name", "email", "state", "firm", "signed_up_at", "source"])
    for entry in active_entries(db):
        writer.writerow(
            [
                entry.name,
                entry.email,
                entry.state,
                entry.firm or "",
                entry.created_at.isoformat(),
                entry.source,
            ]
        )
    return out.getvalue().encode("utf-8")
