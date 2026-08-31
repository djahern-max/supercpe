"""Site mode: the Phase B gate, stored on the sponsor profile and logged.

Every change writes a `site_mode_changes` row and the profile in one
transaction, so the log and the state cannot disagree. Nothing here reads
`may_claim_registry`: the site payload carries only the mode and the
sponsor's display name.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.auth import SITE_MODES
from app.models.account import Account
from app.models.site import SiteModeChange
from app.services.auth import AuthRuleViolation
from app.services.sponsor import get_profile


def get_site_mode(db: Session) -> str:
    return get_profile(db).site_mode


def site_origin() -> str:
    """Where the public site lives, for absolute URLs (017's registration
    links, 021's invitation, 022's sitemap): in prod CORS_ORIGINS is
    exactly https://supercpe.com; in dev the first origin is where the
    frontend lives."""
    return settings.cors_origins_list[0]


def sitemap_paths(db: Session) -> list[str]:
    """What /sitemap.xml lists (022), mode-aware: while coming_soon, only
    the root — the landing page is *meant* to be indexed, so the domain
    has standing by opening day, but everything behind the 009 gate 404s
    and is not announced. At open, the public set: the renderable
    published course pages (the same filter as the catalog — a stale
    credit refuses the page, so the sitemap must not point at it) and the
    fixed public pages."""
    if get_site_mode(db) != "open":
        return ["/"]
    from app.services import courses, credit

    return [
        "/",
        "/courses",
        *(
            f"/courses/{course.course_code}"
            for course in courses.list_published(db)
            if not credit.is_stale(course)
        ),
        "/policies",
        "/certificates/verify",
        "/register",
    ]


def site_open_blockers(db: Session) -> list[str]:
    """What refuses opening the site: the block-level launch findings —
    each 8.01 policy kind with no current version (011), no published
    course passing the 8.01 disclosure completeness check (016), and
    outbound email not configured for production (017). New in 011 —
    009 let the flip through unchecked. Warn-level launch findings
    (evaluation_review_due) are reported on /admin/sponsor but do not
    block: an overdue evaluation review must never be able to close
    enrollment forever."""
    # Deferred import: readiness reaches back into course services.
    from app.services import readiness

    return [
        finding.message
        for finding in readiness.launch_findings(db)
        if finding.level == "block"
    ]


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
    if to_mode == "open":
        blockers = site_open_blockers(db)
        if blockers:
            raise AuthRuleViolation(blockers)
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
