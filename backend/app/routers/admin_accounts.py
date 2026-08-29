import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.schemas.auth import AccountCreate, AccountCreated, AccountOut, RoleRequest
from app.schemas.package import ValidationErrors
from app.services import auth as auth_service
from app.services.auth import AuthRuleViolation

router = APIRouter(prefix="/admin/accounts")


def _get_account_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


def _violation_response(violation: AuthRuleViolation) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": violation.errors})


def _account_out(db: Session, account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        email=account.email,
        role=account.role,
        display_name=account.display_name,
        is_active=account.is_active,
        must_change_password=account.must_change_password,
        created_at=account.created_at,
        deactivated_at=account.deactivated_at,
        last_sign_in=auth_service.last_sign_in(db, account),
        open_sessions=auth_service.open_session_count(db, account),
    )


@router.get("", response_model=list[AccountOut])
def list_accounts(
    db: Session = Depends(get_db),
    _: Account = Depends(require_role("admin")),
):
    accounts = db.scalars(select(Account).order_by(Account.email))
    return [_account_out(db, account) for account in accounts]


@router.post(
    "",
    response_model=AccountCreated,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_role("admin")),
):
    # Generated here, returned once, stored only as a hash. The new account
    # must change it on first login.
    initial_password = secrets.token_urlsafe(12)
    try:
        account = auth_service.create_account(
            db,
            payload.email,
            payload.role,
            initial_password,
            created_by=actor,
            display_name=payload.display_name,
        )
    except AuthRuleViolation as violation:
        return _violation_response(violation)
    return AccountCreated(
        id=account.id,
        email=account.email,
        role=account.role,
        display_name=account.display_name,
        initial_password=initial_password,
    )


@router.put(
    "/{account_id}/role",
    response_model=AccountOut,
    responses={422: {"model": ValidationErrors}},
)
def set_role(
    account_id: int,
    payload: RoleRequest,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_role("admin")),
):
    account = _get_account_or_404(db, account_id)
    try:
        auth_service.set_role(db, account, payload.role, actor)
    except AuthRuleViolation as violation:
        return _violation_response(violation)
    return _account_out(db, account)


@router.post(
    "/{account_id}/deactivate",
    response_model=AccountOut,
    responses={422: {"model": ValidationErrors}},
)
def deactivate(
    account_id: int,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_role("admin")),
):
    account = _get_account_or_404(db, account_id)
    try:
        auth_service.deactivate(db, account, actor)
    except AuthRuleViolation as violation:
        return _violation_response(violation)
    return _account_out(db, account)


@router.post("/{account_id}/reactivate", response_model=AccountOut)
def reactivate(
    account_id: int,
    db: Session = Depends(get_db),
    _: Account = Depends(require_role("admin")),
):
    account = _get_account_or_404(db, account_id)
    auth_service.reactivate(db, account)
    return _account_out(db, account)


@router.post("/{account_id}/revoke-sessions", response_model=AccountOut)
def revoke_sessions(
    account_id: int,
    db: Session = Depends(get_db),
    _: Account = Depends(require_role("admin")),
):
    account = _get_account_or_404(db, account_id)
    auth_service.revoke_all_sessions(db, account)
    return _account_out(db, account)
