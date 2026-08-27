from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models.sme import SubjectMatterExpert
from app.schemas.package import ValidationErrors
from app.schemas.sme import SmeCreate, SmeOut, SmeUpdate
from app.services import smes
from app.services.courses import CourseRuleViolation

router = APIRouter(prefix="/admin/smes", dependencies=[Depends(require_admin)])


def _get_sme_or_404(db: Session, sme_id: int) -> SubjectMatterExpert:
    sme = smes.get_sme(db, sme_id)
    if sme is None:
        raise HTTPException(status_code=404, detail="Subject matter expert not found")
    return sme


@router.get("", response_model=list[SmeOut])
def list_smes(db: Session = Depends(get_db)):
    return smes.list_smes(db)


@router.post("", response_model=SmeOut, status_code=201)
def create_sme(payload: SmeCreate, db: Session = Depends(get_db)):
    return smes.create_sme(db, **payload.model_dump())


@router.get("/{sme_id}", response_model=SmeOut)
def get_sme(sme_id: int, db: Session = Depends(get_db)):
    return _get_sme_or_404(db, sme_id)


@router.patch("/{sme_id}", response_model=SmeOut)
def update_sme(sme_id: int, payload: SmeUpdate, db: Session = Depends(get_db)):
    sme = _get_sme_or_404(db, sme_id)
    return smes.update_sme(db, sme, **payload.model_dump())


@router.delete(
    "/{sme_id}", status_code=204, responses={422: {"model": ValidationErrors}}
)
def delete_sme(sme_id: int, db: Session = Depends(get_db)):
    sme = _get_sme_or_404(db, sme_id)
    try:
        smes.delete_sme(db, sme)
    except CourseRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
