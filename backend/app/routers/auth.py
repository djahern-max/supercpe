"""Login, logout, and the current account.

CSRF posture: the session cookie is SameSite=Lax, CORS is same-origin, and
every mutating route here requires `Content-Type: application/json`, which
a cross-site form cannot send. No CSRF token is needed on top of that.
These routes are never gated on site mode: /login must work while the
site is coming_soon. The two exceptions are 030's Google routes, which
answer the 009 gate's 404 anonymously while coming_soon and are public at
open — with 030a's one door: while `GOOGLE_PREVIEW_EMAILS` names at
least one address, the config route answers its public client id and
the sign-in route completes for a Google-verified address on that list,
so the operator can walk Google sign-in on the closed production site.
Everyone else still meets the gate's 404, byte for byte.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import (
    current_account,
    require_role,
    site_gate_refusal,
    site_open_or_session,
)
from app.config import settings
from app.constants.auth import SESSION_ABSOLUTE_HOURS, SESSION_COOKIE
from app.constants.jurisdictions import US_JURISDICTIONS
from app.db import get_db
from app.models.account import Account
from app.schemas.auth import (
    ChangePasswordRequest,
    GoogleConfigOut,
    GoogleSignInRequest,
    LoginRequest,
    MeOut,
    MyStateOut,
    MyStateRequest,
)
from app.schemas.package import ValidationErrors
from app.services import auth as auth_service
from app.services import google_identity
from app.services import subscriptions as subscriptions_service
from app.services.google_identity import GoogleIdentityError
from app.services.auth import AuthenticationFailed, AuthRuleViolation

router = APIRouter(prefix="/auth")


def require_json(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/json"
        )


def require_site_open_or_session_or_preview_list(
    request: Request, db: Session = Depends(get_db)
) -> None:
    """030a: the 009 gate on the two Google routes, with one difference —
    while the operator has named an address in GOOGLE_PREVIEW_EMAILS the
    routes answer past it and decide for themselves: the config route
    gives its client id (public by construction: it ships in every page
    that renders Google's button, and says nothing about a course, a
    price, or a participant); the sign-in route repeats the gate's 404
    unless the token's verified email is listed (`_preview_listed`). With
    the list empty this *is* `require_site_open_or_session`, and it runs
    before the body is parsed, so an anonymous malformed request on a
    closed site still gets the 404 it got in 030, never a 422."""
    if settings.google_preview_email_set:
        return
    if not site_open_or_session(request, db):
        raise site_gate_refusal()


def _preview_listed(credential: str) -> bool:
    """030a: whether a Google-signed token names an address on the
    operator's list. Verified at the boundary first; a bad token, an
    unverified email, and an unlisted one all answer False, and the
    caller gives the gate's 404 for each — the same body a route that
    does not exist gives, so nothing is learned. Reads and writes no
    database row: the allowlist decides before `sign_in_with_google`
    (which verifies the token again — one cached-JWKS signature check,
    accepted so the service stays untouched) ever runs."""
    if not settings.google_preview_email_set:
        return False
    try:
        identity = google_identity.verify(credential)
    except GoogleIdentityError:
        return False
    if not identity.email_verified:
        return False
    return identity.email.strip().lower() in settings.google_preview_email_set


def _me(db: Session, account: Account) -> MeOut:
    return MeOut(
        id=account.id,
        email=account.email,
        role=account.role,
        display_name=account.display_name,
        must_change_password=account.must_change_password,
        subscription_current=(
            account.role == "participant"
            and subscriptions_service.current(db, account) is not None
        ),
        signin_methods=auth_service.signin_methods(account),
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
    return _me(db, account)


@router.get(
    "/google/config",
    response_model=GoogleConfigOut,
    dependencies=[Depends(require_site_open_or_session_or_preview_list)],
)
def google_config():
    """030: the client id the button needs, or null — the frontend renders
    Google's button only when it is non-null. Nothing else is exposed.
    030a: answers anonymously on a closed site only while the preview
    list is non-empty (the dependency decides)."""
    return GoogleConfigOut(client_id=settings.google_client_id or None)


@router.post(
    "/google",
    response_model=MeOut,
    dependencies=[
        Depends(require_site_open_or_session_or_preview_list),
        Depends(require_json),
    ],
)
def google_sign_in(
    payload: GoogleSignInRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """030: sign in (or create a participant account) from a Google ID
    token. Same session function, same cookie, same response shape as
    password login; one constant 401 for every refusal. 030a: a closed
    site with no session completes only for a listed address; every
    other token gets the gate's 404, and from here on nothing forks on
    site mode."""
    if not site_open_or_session(request, db) and not _preview_listed(
        payload.credential
    ):
        raise site_gate_refusal()
    try:
        account = auth_service.sign_in_with_google(db, payload.credential)
    except AuthenticationFailed:
        raise HTTPException(
            status_code=401, detail=auth_service.GOOGLE_SIGN_IN_FAILED
        )
    raw_token = auth_service.open_session(
        db,
        account,
        user_agent=request.headers.get("user-agent", ""),
        ip=request.client.host if request.client else "",
    )
    _set_session_cookie(response, raw_token)
    return _me(db, account)


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
def me(
    db: Session = Depends(get_db),
    account: Account = Depends(current_account),
):
    return _me(db, account)


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
    return _me(db, account)
