"""015: the two coming_soon carve-outs from the 009 site gate.

These routes are the inverse of `require_site_open_or_session`: they
exist only while `site_mode` is `coming_soon` and 404 the moment the
site opens — the waiting list stops accepting entries then, and 021
mails the people already on it.

The landing payload has no field for course facts, credit figures,
objectives, or prices: 8.01 attaches its eleven-item disclosure to
descriptive materials, superCPE cannot satisfy the list yet, and a page
that discloses some of the items is worse than one that discloses none.
016 owns the full disclosure. Nothing here may contain the words
"National Registry" or a sponsor ID (003's rule): `may_claim_registry`
is the boolean the page reads, never the words themselves.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.package import ValidationErrors
from app.schemas.waiting_list import (
    LandingOut,
    WaitingListJoined,
    WaitingListRequest,
)
from app.services import policies as policies_service
from app.services import site as site_service
from app.services import waiting_list as waiting_list_service
from app.services.sponsor import get_profile
from app.services.waiting_list import WaitingListRuleViolation


def require_coming_soon(db: Session = Depends(get_db)) -> None:
    """404 — not 403 — when the site is open, mirroring how the closed
    site hides what is behind it (009): an open site does not advertise
    that a waiting list ever existed."""
    if site_service.get_site_mode(db) != "coming_soon":
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(dependencies=[Depends(require_coming_soon)])

# One body for every signup outcome — first, repeat, honeypot — so the
# response never says whether a row exists or was created.
JOINED = WaitingListJoined(
    message=(
        "You're on the list. We'll send one email when the course opens "
        "— nothing else."
    )
)


@router.get("/landing", response_model=LandingOut)
def get_landing(db: Session = Depends(get_db)):
    profile = get_profile(db)
    return LandingOut(
        sponsor_name=profile.name,
        may_claim_registry=profile.may_claim_registry,
        policies_published=not policies_service.missing_kinds(db),
    )


@router.post(
    "/waiting-list",
    response_model=WaitingListJoined,
    responses={422: {"model": ValidationErrors}},
)
def join_waiting_list(
    payload: WaitingListRequest, db: Session = Depends(get_db)
):
    if payload.website.strip():
        # Honeypot tripped: same 200, nothing stored, a bot learns nothing.
        return JOINED
    try:
        waiting_list_service.sign_up(
            db, payload.name, payload.email, payload.state, payload.firm
        )
    except WaitingListRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return JOINED
