"""Public certificate verification (019, 9.01.1).

Anyone a participant hands their certificate to — a state board, an
employer — can confirm it is real by the code printed on it. The route
sits behind `require_site_open_or_session` like every Phase C route:
public at `open`, 404 anonymously in `coming_soon` (nothing is added to
the 015 walk's allowlist).

The namespace deliberately avoids 017's `/verify` (email verification);
both resolve independently, pinned by test. Unknown and malformed codes
answer the exact not-found shape the site gate itself uses — no existence
oracle, no distinction.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_site_open_or_session
from app.db import get_db
from app.models.enrollment import Completion
from app.schemas.certificates import CertificateVerificationOut

router = APIRouter(
    prefix="/certificates",
    dependencies=[Depends(require_site_open_or_session)],
)

# Byte-identical to the site gate's refusal (app/auth.py): a bad code at
# open answers exactly like any route at coming_soon.
NOT_FOUND = "Not found"


@router.get("/verify/{code}", response_model=CertificateVerificationOut)
def verify_certificate(code: str, db: Session = Depends(get_db)):
    completion = db.scalar(
        select(Completion).where(Completion.verification_token == code)
    )
    if completion is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    snapshot = completion.certificate_snapshot
    return CertificateVerificationOut(
        valid=True,
        # The same fallback the certificate itself prints (010): the page
        # confirms what the paper says.
        participant_name=snapshot["participant_name"]
        or snapshot["participant_email"],
        course_title=snapshot["course_title"],
        field_of_study=snapshot["field_of_study"],
        credit=snapshot["credit"],
        completed_at=snapshot["completed_at"][:10],
        sponsor_name=snapshot["sponsor_name"],
        program_type=snapshot["program_type"],
    )
