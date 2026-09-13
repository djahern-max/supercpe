"""Request dependencies for accounts, roles, and the site-mode gate.

Role hierarchy is explicit, not implied: `require_role` checks membership
in exactly the roles listed, so `admin` appears wherever admins are
allowed. Authentication failures are 401 with one fixed detail;
authorization failures are 403.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.constants.auth import SESSION_COOKIE
from app.db import get_db
from app.models.account import Account
from app.services import auth as auth_service
from app.services import site as site_service

NOT_AUTHENTICATED = "Not authenticated"


def _resolve_account(request: Request, db: Session) -> Account | None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return None
    return auth_service.resolve_session(db, raw_token)


def current_account(
    request: Request, db: Session = Depends(get_db)
) -> Account:
    """Any valid session, any role, even mid forced password change. Only
    the auth routes themselves (/me, /change-password, /logout...) use
    this; everything else goes through require_role."""
    account = _resolve_account(request, db)
    if account is None:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)
    return account


def optional_account(
    request: Request, db: Session = Depends(get_db)
) -> Account | None:
    """The account behind the session, or None — for routes whose answer
    is per-viewer but whose absence must look like absence: 020's
    jurisdiction hint answers 404, never 401, so it does not advertise
    that a hint exists for somebody else."""
    return _resolve_account(request, db)


def require_role(*roles: str):
    """Dependency factory: a valid session whose account holds one of the
    named roles. While `must_change_password` is set, every route behind
    this refuses with 403 until the password is changed."""

    def dependency(
        request: Request, db: Session = Depends(get_db)
    ) -> Account:
        account = _resolve_account(request, db)
        if account is None:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)
        if account.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        if account.must_change_password:
            raise HTTPException(status_code=403, detail="must_change_password")
        return account

    return dependency


def site_gate_refusal() -> HTTPException:
    """The gate's one answer: 404 — not 401 — so a closed site does not
    advertise what is behind it. A route that refuses on the gate's
    behalf from inside its handler (030a's Google sign-in) raises this,
    never a 404 of its own, so the two cannot drift apart."""
    return HTTPException(status_code=404, detail="Not found")


def site_open_or_session(request: Request, db: Session) -> bool:
    """The gate's predicate: open site, or any valid session. Callable
    from a handler as well as from the dependency below (030a)."""
    if site_service.get_site_mode(db) == "open":
        return True
    return _resolve_account(request, db) is not None


def require_site_open_or_session(
    request: Request, db: Session = Depends(get_db)
) -> None:
    """The Phase B gate on public routes: open site, or any valid session."""
    if not site_open_or_session(request, db):
        raise site_gate_refusal()
