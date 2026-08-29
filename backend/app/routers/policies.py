"""The published policies (8.01 items 8-11) and the 4.05.3 item 4
instructions page.

The public routes sit behind `require_site_open_or_session` exactly like
the catalog: 8.01.1 wants the policies published in advance of
participation, and while the site is coming-soon, "participation" is
sessions only. The admin routes publish new versions; there is no edit or
delete — corrections are new versions.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role, require_site_open_or_session
from app.db import get_db
from app.models.account import Account
from app.models.policy import POLICY_KINDS
from app.schemas.package import ValidationErrors
from app.schemas.policy import (
    AdminPoliciesOut,
    HowItWorksOut,
    PoliciesPublicOut,
    PolicyPublish,
    PolicyVersionOut,
)
from app.services import policies as policies_service
from app.services.instructions import how_it_works_markdown
from app.services.policies import PolicyRuleViolation

router = APIRouter(dependencies=[Depends(require_site_open_or_session)])
admin_router = APIRouter(
    prefix="/admin/policies", dependencies=[Depends(require_role("admin"))]
)


@router.get("/policies", response_model=PoliciesPublicOut)
def get_policies(db: Session = Depends(get_db)):
    return PoliciesPublicOut(**policies_service.current(db))


@router.get("/how-it-works", response_model=HowItWorksOut)
def get_how_it_works():
    return HowItWorksOut(markdown=how_it_works_markdown())


def _admin_view(db: Session) -> AdminPoliciesOut:
    history = []
    for kind in POLICY_KINDS:
        current = policies_service.current_version(db, kind)
        history += [
            PolicyVersionOut(
                id=version.id,
                kind=version.kind,
                body=version.body,
                effective_at=version.effective_at,
                created_at=version.created_at,
                created_by_email=version.created_by.email,
                is_current=current is not None and version.id == current.id,
            )
            for version in policies_service.versions_of(db, kind)
        ]
    return AdminPoliciesOut(
        history=history, missing=policies_service.missing_kinds(db)
    )


@admin_router.get("", response_model=AdminPoliciesOut)
def list_policies(db: Session = Depends(get_db)):
    return _admin_view(db)


@admin_router.post(
    "",
    response_model=AdminPoliciesOut,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def publish_policy(
    payload: PolicyPublish,
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("admin")),
):
    try:
        policies_service.publish(
            db, payload.kind, payload.body, payload.effective_at, account
        )
    except PolicyRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return _admin_view(db)
