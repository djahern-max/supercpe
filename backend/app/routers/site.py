"""Site mode: the always-public site payload and the admin switch.

`GET /site` is never gated — it is how the frontend learns which page to
render. It carries only the mode and the sponsor's display name; nothing
here reads `may_claim_registry` and no response may contain the words
"National Registry" or a sponsor ID.
"""

from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.schemas.auth import SiteModeChangeOut, SiteModeRequest, SiteOut
from app.schemas.package import ValidationErrors
from app.services import site as site_service
from app.services.auth import AuthRuleViolation
from app.services.sponsor import get_profile

router = APIRouter()
admin_router = APIRouter(prefix="/admin")


@router.get("/site", response_model=SiteOut)
def get_site(db: Session = Depends(get_db)):
    profile = get_profile(db)
    return SiteOut(site_mode=profile.site_mode, sponsor_name=profile.name)


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    """022: mode-aware sitemap, intentionally public like /site — indexing
    is meant to start while coming_soon, so the mechanism lives with the
    mode it reads. Caddy rewrites the site-root /sitemap.xml here. The
    URLs are frontend pages on the public origin, never API routes."""
    origin = site_service.site_origin()
    urls = "\n".join(
        f"  <url><loc>{escape(f'{origin}{path}')}</loc></url>"
        for path in site_service.sitemap_paths(db)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


def _changes(db: Session) -> list[SiteModeChangeOut]:
    return [
        SiteModeChangeOut(
            id=change.id,
            from_mode=change.from_mode,
            to_mode=change.to_mode,
            changed_by_email=change.changed_by.email,
            changed_at=change.changed_at,
            note=change.note,
        )
        for change in site_service.list_changes(db)
    ]


@admin_router.put(
    "/site-mode",
    response_model=list[SiteModeChangeOut],
    responses={422: {"model": ValidationErrors}},
)
def set_site_mode(
    payload: SiteModeRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("admin")),
):
    try:
        site_service.set_site_mode(db, payload.site_mode, account, payload.note)
    except AuthRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return _changes(db)


@admin_router.get("/site-mode/changes", response_model=list[SiteModeChangeOut])
def list_site_mode_changes(
    db: Session = Depends(get_db),
    _: Account = Depends(require_role("admin")),
):
    return _changes(db)
