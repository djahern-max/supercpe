from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.sponsor import SponsorProfilePublic
from app.services import sponsor

router = APIRouter()


@router.get(
    "/sponsor", response_model=SponsorProfilePublic, response_model_exclude_none=True
)
def get_public_sponsor(db: Session = Depends(get_db)):
    profile = sponsor.get_profile(db)
    return SponsorProfilePublic(
        name=profile.name,
        website=profile.website,
        # Never expose a sponsor ID unless the sponsor may claim Registry
        # membership; exclude_none drops the field entirely.
        national_registry_id=(
            profile.national_registry_id if profile.may_claim_registry else None
        ),
    )
