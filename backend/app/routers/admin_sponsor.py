from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.sponsor import SponsorProfile
from app.schemas.package import ValidationErrors
from app.schemas.sponsor import (
    SponsorProfileAdmin,
    SponsorProfileUpdate,
    StateRegistration,
)
from app.services import sponsor
from app.services.sponsor import SponsorRuleViolation

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])


def _admin_view(db: Session, profile: SponsorProfile) -> SponsorProfileAdmin:
    return SponsorProfileAdmin(
        name=profile.name,
        legal_name=profile.legal_name,
        registry_status=profile.registry_status,
        national_registry_id=profile.national_registry_id,
        website=profile.website,
        contact_email=profile.contact_email,
        contact_phone=profile.contact_phone,
        address=profile.address,
        other_certificate_statements=profile.other_certificate_statements,
        updated_at=profile.updated_at,
        missing_fields=profile.missing_fields(),
        may_claim_registry=profile.may_claim_registry,
        state_registrations=[
            StateRegistration.model_validate(row)
            for row in sponsor.get_state_registrations(db)
        ],
    )


@router.get("/sponsor", response_model=SponsorProfileAdmin)
def get_sponsor(db: Session = Depends(get_db)):
    return _admin_view(db, sponsor.get_profile(db))


@router.put(
    "/sponsor",
    response_model=SponsorProfileAdmin,
    responses={422: {"model": ValidationErrors}},
)
def update_sponsor(payload: SponsorProfileUpdate, db: Session = Depends(get_db)):
    try:
        profile = sponsor.update_profile(db, payload.model_dump())
    except SponsorRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return _admin_view(db, profile)


@router.put(
    "/sponsor/state-registrations",
    response_model=list[StateRegistration],
    responses={422: {"model": ValidationErrors}},
)
def put_state_registrations(
    payload: list[StateRegistration], db: Session = Depends(get_db)
):
    try:
        rows = sponsor.set_state_registrations(
            db, [row.model_dump() for row in payload]
        )
    except SponsorRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return rows
