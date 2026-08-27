"""Sponsor profile reads and writes.

Rule violations raise `SponsorRuleViolation` carrying the error strings for
the router to wrap in a 422 `{"errors": [...]}`, the same response shape as
package ingest.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.sponsor import SponsorProfile, SponsorStateRegistration

REGISTERED_NEEDS_ID = (
    "registry_status is 'registered' but national_registry_id is blank. "
    "A Registry sponsor has a sponsor ID; enter it."
)
NOT_REGISTERED_FORBIDS_ID = (
    "registry_status is 'not_registered' but national_registry_id is set. "
    "A sponsor that is not on the National Registry does not have a sponsor "
    "ID and may not claim one."
)


class SponsorRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def get_profile(db: Session) -> SponsorProfile:
    """Always returns the singleton row. The migration inserts it, so it is
    only ever absent in a database built by `create_all` (tests); creating
    it here keeps those databases honest."""
    profile = db.get(SponsorProfile, 1)
    if profile is None:
        profile = SponsorProfile(id=1)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_profile(db: Session, data: dict) -> SponsorProfile:
    # Refuse the registry-status contradictions with a message naming the
    # rule before the CHECK constraint ever fires.
    status = data["registry_status"]
    registry_id = data["national_registry_id"].strip()
    if status == "registered" and registry_id == "":
        raise SponsorRuleViolation([REGISTERED_NEEDS_ID])
    if status == "not_registered" and registry_id != "":
        raise SponsorRuleViolation([NOT_REGISTERED_FORBIDS_ID])

    profile = get_profile(db)
    for field, value in data.items():
        setattr(profile, field, value.strip() if field == "national_registry_id" else value)
    db.commit()
    db.refresh(profile)
    return profile


def get_state_registrations(db: Session) -> list[SponsorStateRegistration]:
    return list(
        db.execute(
            select(SponsorStateRegistration).order_by(SponsorStateRegistration.state)
        ).scalars()
    )


def set_state_registrations(
    db: Session, rows: list[dict]
) -> list[SponsorStateRegistration]:
    """Replaces the full set atomically."""
    states = [row["state"] for row in rows]
    duplicates = sorted({state for state in states if states.count(state) > 1})
    if duplicates:
        raise SponsorRuleViolation(
            [f"Duplicate state in payload: {state}" for state in duplicates]
        )

    db.execute(delete(SponsorStateRegistration))
    db.add_all(SponsorStateRegistration(**row) for row in rows)
    db.commit()
    return get_state_registrations(db)
