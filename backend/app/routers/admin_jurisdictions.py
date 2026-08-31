"""020: the per-jurisdiction credit policy table.

Always 55 rows out — the US_JURISDICTIONS codes — whether or not a
database row exists yet (create on edit). Each row says live whether it
is displayable to participants and whether its verification has gone
stale; the admin researching and re-verifying these against board
sources is an OPERATIONS.md responsibility, not code's.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role
from app.constants.jurisdictions import US_JURISDICTIONS
from app.db import get_db
from app.models.account import Account
from app.models.jurisdiction import JurisdictionPolicy
from app.schemas.jurisdiction import AdminJurisdictionOut, JurisdictionUpdate
from app.schemas.package import ValidationErrors
from app.services import jurisdictions as jurisdictions_service
from app.services.jurisdictions import JurisdictionRuleViolation

router = APIRouter(
    prefix="/admin/jurisdictions",
    dependencies=[Depends(require_role("admin"))],
)


def _out(code: str, row: JurisdictionPolicy | None) -> AdminJurisdictionOut:
    return AdminJurisdictionOut(
        jurisdiction=code,
        name=US_JURISDICTIONS[code],
        credit_increment=row.credit_increment if row else "unknown",
        non_technical_cap_note=row.non_technical_cap_note if row else "",
        source=row.source if row else "",
        verified_on=row.verified_on if row else None,
        notes=row.notes if row else "",
        displayable=jurisdictions_service.displayable(row),
        verification_stale=(
            jurisdictions_service.verification_stale(row) if row else False
        ),
    )


@router.get("", response_model=list[AdminJurisdictionOut])
def list_jurisdictions(
    db: Session = Depends(get_db),
    _: Account = Depends(require_role("admin")),
):
    rows = jurisdictions_service.all_rows(db)
    return [_out(code, rows.get(code)) for code in US_JURISDICTIONS]


@router.put(
    "/{code}",
    response_model=AdminJurisdictionOut,
    responses={422: {"model": ValidationErrors}},
)
def update_jurisdiction(
    code: str,
    payload: JurisdictionUpdate,
    db: Session = Depends(get_db),
    _: Account = Depends(require_role("admin")),
):
    try:
        row = jurisdictions_service.upsert(
            db,
            code.upper(),
            payload.credit_increment,
            payload.non_technical_cap_note,
            payload.source,
            payload.verified_on,
            payload.notes,
        )
    except JurisdictionRuleViolation as violation:
        return JSONResponse(
            status_code=422, content={"errors": violation.errors}
        )
    return _out(row.jurisdiction, row)
