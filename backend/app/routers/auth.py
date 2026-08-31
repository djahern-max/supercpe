"""Login, logout, and the current account.

CSRF posture: the session cookie is SameSite=Lax, CORS is same-origin, and
every mutating route here requires `Content-Type: application/json`, which
a cross-site form cannot send. No CSRF token is needed on top of that.
These routes are never gated on site mode: /login must work while the
site is coming_soon.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import current_account, require_role
from app.config import settings
from app.constants.auth import SESSION_ABSOLUTE_HOURS, SESSION_COOKIE
from app.constants.jurisdictions import US_JURISDICTIONS
from app.db import get_db
from app.models.account import Account
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeOut,
    MyStateOut,
    MyStateRequest,
)
from app.schemas.package import ValidationErrors
from app.services import auth as auth_service
from app.services.auth import AuthenticationFailed, AuthRuleViolation

router = APIRouter(prefix="/auth")


def require_json(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/json"
        )


def _me(account: Account) -> MeOut:
    return MeOut(
        id=account.id,
        email=account.email,
        role=account.role,
        display_name=account.display_name,
        must_change_password=account.must_change_password,
    )


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=SESSION_ABSOLUTE_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=not settings.dev,
        path="/",
    )


@router.post(
    "/login", response_model=MeOut, dependencies=[Depends(require_json)]
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        account = auth_service.authenticate(db, payload.email, payload.password)
    except AuthenticationFailed:
        raise HTTPException(status_code=401, detail=auth_service.LOGIN_FAILED)
    raw_token = auth_service.open_session(
        db,
        account,
        user_agent=request.headers.get("user-agent", ""),
        ip=request.client.host if request.client else "",
    )
    _set_session_cookie(response, raw_token)
    return _me(account)


@router.post("/logout", status_code=204, dependencies=[Depends(require_json)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        auth_service.revoke_session(db, raw_token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post(
    "/logout-all", status_code=204, dependencies=[Depends(require_json)]
)
def logout_all(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    account: Account = Depends(current_account),
):
    auth_service.revoke_all_sessions(db, account)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeOut)
def me(account: Account = Depends(current_account)):
    return _me(account)


@router.get("/me/state", response_model=MyStateOut)
def my_state(
    account: Account = Depends(require_role("participant")),
):
    """020: the state of licensure the jurisdiction hint keys on. The
    participant's claim about themselves, not a credential — no
    verification step, and it never reaches a certificate."""
    return MyStateOut(state=account.state)


@router.put(
    "/me/state",
    response_model=MyStateOut,
    dependencies=[Depends(require_json)],
    responses={422: {"model": ValidationErrors}},
)
def set_my_state(
    payload: MyStateRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("participant")),
):
    state = (payload.state or "").strip().upper()
    if state and state not in US_JURISDICTIONS:
        return JSONResponse(
            status_code=422,
            content={
                "errors": [
                    f'"{state}" is not a two-letter US licensing '
                    "jurisdiction code"
                ]
            },
        )
    account.state = state or None
    db.commit()
    return MyStateOut(state=account.state)


@router.post(
    "/change-password",
    response_model=MeOut,
    dependencies=[Depends(require_json)],
    responses={422: {"model": ValidationErrors}},
)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(current_account),
):
    raw_token = request.cookies.get(SESSION_COOKIE, "")
    try:
        auth_service.change_password(
            db,
            account,
            payload.current_password,
            payload.new_password,
            raw_token,
        )
    except AuthRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return _me(account)
