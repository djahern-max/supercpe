"""Sponsor profile reads and writes.

Rule violations raise `SponsorRuleViolation` carrying the error strings for
the router to wrap in a 422 `{"errors": [...]}`, the same response shape as
package ingest.
"""

from io import BytesIO

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.constants.certificate import LOGO_MAX_BYTES, LOGO_MEDIA_TYPES
from app.models.sponsor import SponsorProfile, SponsorStateRegistration
from app.services.certificates import Logo
from app.storage import Storage

LOGO_KEY_PREFIX = "sponsor/logo"
LOGO_NOT_AN_IMAGE = (
    "The logo must be a PNG or an SVG file; the upload was neither."
)
LOGO_TOO_LARGE = f"The logo must be {LOGO_MAX_BYTES // (1024 * 1024)} MB or smaller."

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


# --- the certificate mark (032) ---------------------------------------------


def _logo_extension(content: bytes) -> str | None:
    """"png" or "svg" from the bytes themselves, never the filename or
    the declared content type."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    head = content[:4096].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or head.startswith(b"<!"):
        if b"<svg" in head:
            return "svg"
    return None


def set_logo(db: Session, storage: Storage, content: bytes) -> SponsorProfile:
    """Store the uploaded mark at `sponsor/logo.<ext>` and point the
    profile at it. Presentation only: nothing here touches a snapshot or
    a stored certificate."""
    if len(content) > LOGO_MAX_BYTES:
        raise SponsorRuleViolation([LOGO_TOO_LARGE])
    extension = _logo_extension(content)
    if extension is None:
        raise SponsorRuleViolation([LOGO_NOT_AN_IMAGE])
    key = f"{LOGO_KEY_PREFIX}.{extension}"
    storage.put(key, BytesIO(content))
    profile = get_profile(db)
    profile.logo_path = key
    db.commit()
    db.refresh(profile)
    return profile


def clear_logo(db: Session) -> SponsorProfile:
    """Back to the brand logo (033). The stored object is left in place — it is
    overwritten by the next upload of the same type, and nothing at the
    storage boundary deletes."""
    profile = get_profile(db)
    profile.logo_path = None
    db.commit()
    db.refresh(profile)
    return profile


def load_logo(db: Session, storage: Storage) -> Logo | None:
    """The uploaded mark as bytes for `certificates.render`, or None for
    the brand logo. A profile row absent (create_all databases) or a key
    whose object is gone both read as None: a certificate is never
    refused for want of decoration."""
    profile = db.get(SponsorProfile, 1)
    if profile is None or not profile.logo_path:
        return None
    if not storage.exists(profile.logo_path):
        return None
    extension = profile.logo_path.rsplit(".", 1)[-1]
    with storage.open(profile.logo_path) as file:
        return Logo(file.read(), LOGO_MEDIA_TYPES[extension])
