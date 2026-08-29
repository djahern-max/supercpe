"""Site mode: the Phase B gate, stored on the sponsor profile and logged.

Every change writes a `site_mode_changes` row and the profile in one
transaction, so the log and the state cannot disagree. Nothing here reads
`may_claim_registry`: the site payload carries only the mode and the
sponsor's display name.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.auth import SITE_MODES
from app.models.account import Account
from app.models.site import SiteModeChange
from app.services.auth import AuthRuleViolation
from app.services.sponsor import get_profile


def get_site_mode(db: Session) -> str:
    return get_profile(db).site_mode


def set_site_mode(
    db: Session, to_mode: str, account: Account, note: str = ""
) -> SiteModeChange:
    if to_mode not in SITE_MODES:
        raise AuthRuleViolation(
            [f'site_mode must be one of {", ".join(SITE_MODES)}, not "{to_mode}"']
        )
    profile = get_profile(db)
    if profile.site_mode == to_mode:
        raise AuthRuleViolation(
            [f"The site mode is already {to_mode}; nothing to change."]
        )
    change = SiteModeChange(
        from_mode=profile.site_mode,
        to_mode=to_mode,
        changed_by_account_id=account.id,
        note=note,
    )
    profile.site_mode = to_mode
    db.add(change)
    db.commit()
    return change


def list_changes(db: Session) -> list[SiteModeChange]:
    """Newest first."""
    return list(
        db.scalars(
            select(SiteModeChange).order_by(
                SiteModeChange.changed_at.desc(), SiteModeChange.id.desc()
            )
        )
    )
