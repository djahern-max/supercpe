"""Accounts and sessions: the server-vouched identity 6.01 requires.

Authentication failures (login) are deliberately uniform: unknown email,
wrong password, and inactive account all raise `AuthenticationFailed` with
the same message, and unknown emails still cost a hash verification so the
response time does not say which it was. Rule violations raise
`AuthRuleViolation` carrying error strings for the router to wrap in the
same 422 `{"errors": [...]}` shape as every prior feature.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.auth import (
    LOCKOUT_MINUTES,
    MAX_FAILED_LOGINS,
    MIN_PASSWORD_LENGTH,
    ROLES,
    SESSION_ABSOLUTE_HOURS,
    SESSION_IDLE_MINUTES,
)
from app.models.account import Account, AuthSession

LOGIN_FAILED = "Email or password is incorrect"

_hasher = PasswordHasher()
# Verified against on unknown emails so they cost the same as known ones.
_DUMMY_HASH = _hasher.hash("supercpe-dummy-password")


class AuthRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class AuthenticationFailed(Exception):
    """Always carries LOGIN_FAILED; the login route turns it into a 401."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthRuleViolation(
            [f"The password must be at least {MIN_PASSWORD_LENGTH} characters"]
        )


def get_account_by_email(db: Session, email: str) -> Account | None:
    return db.scalar(select(Account).where(Account.email == email.lower()))


def create_account(
    db: Session,
    email: str,
    role: str,
    initial_password: str,
    created_by: Account | None,
    display_name: str = "",
    must_change_password: bool = True,
) -> Account:
    email = email.strip().lower()
    errors = []
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        errors.append(f'"{email}" is not an email address')
    if role not in ROLES:
        errors.append(f'role must be one of {", ".join(ROLES)}, not "{role}"')
    if get_account_by_email(db, email) is not None:
        errors.append(f"An account with email {email} already exists")
    if errors:
        raise AuthRuleViolation(errors)
    _check_password_strength(initial_password)

    account = Account(
        email=email,
        password_hash=_hasher.hash(initial_password),
        role=role,
        display_name=display_name,
        must_change_password=must_change_password,
        created_by_account_id=created_by.id if created_by else None,
    )
    db.add(account)
    db.commit()
    return account


def authenticate(db: Session, email: str, password: str) -> Account:
    account = get_account_by_email(db, email)
    if account is None:
        # Same cost as a real verification, same message as a wrong password.
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerifyMismatchError:
            pass
        raise AuthenticationFailed(LOGIN_FAILED)

    if account.locked_until is not None and account.locked_until > _now():
        raise AuthenticationFailed(LOGIN_FAILED)

    try:
        _hasher.verify(account.password_hash, password)
    except VerifyMismatchError:
        account.failed_logins += 1
        if account.failed_logins >= MAX_FAILED_LOGINS:
            account.locked_until = _now() + timedelta(minutes=LOCKOUT_MINUTES)
            account.failed_logins = 0
        db.commit()
        raise AuthenticationFailed(LOGIN_FAILED)

    if not account.is_active:
        raise AuthenticationFailed(LOGIN_FAILED)

    account.failed_logins = 0
    account.locked_until = None
    db.commit()
    return account


def open_session(
    db: Session, account: Account, user_agent: str = "", ip: str = ""
) -> str:
    """Returns the raw token for the cookie; only its hash is stored."""
    raw_token = secrets.token_urlsafe(32)
    session = AuthSession(
        account_id=account.id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=_now() + timedelta(hours=SESSION_ABSOLUTE_HOURS),
        user_agent=user_agent[:500],
        ip=ip[:100],
    )
    db.add(session)
    db.commit()
    return raw_token


def session_is_valid(session: AuthSession, now: datetime) -> bool:
    """The one place session validity is derived. Not revoked, inside the
    absolute expiry, and seen within the idle window."""
    return (
        session.revoked_at is None
        and session.expires_at > now
        and session.last_seen_at + timedelta(minutes=SESSION_IDLE_MINUTES) > now
    )


def resolve_session(db: Session, raw_token: str) -> Account | None:
    """The account behind a cookie token, bumping last_seen_at; None for a
    missing, revoked, expired, or idle-expired session, or an inactive
    account."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    )
    if session is None or not session_is_valid(session, _now()):
        return None
    if not session.account.is_active:
        return None
    session.last_seen_at = _now()
    db.commit()
    return session.account


def revoke_session(db: Session, raw_token: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    )
    if session is not None and session.revoked_at is None:
        session.revoked_at = _now()
        db.commit()


def revoke_all_sessions(
    db: Session, account: Account, except_token_hash: str | None = None
) -> None:
    now = _now()
    for session in account.sessions:
        if session.revoked_at is None and session.token_hash != except_token_hash:
            session.revoked_at = now
    db.commit()


def open_session_count(db: Session, account: Account) -> int:
    now = _now()
    return sum(
        1 for session in account.sessions if session_is_valid(session, now)
    )


def last_sign_in(db: Session, account: Account) -> datetime | None:
    return db.scalar(
        select(func.max(AuthSession.created_at)).where(
            AuthSession.account_id == account.id
        )
    )


def change_password(
    db: Session, account: Account, current: str, new: str, raw_token: str
) -> None:
    """Verifies the current password, sets the new one, clears the forced
    change, and revokes every session except the one making the change."""
    try:
        _hasher.verify(account.password_hash, current)
    except VerifyMismatchError:
        raise AuthRuleViolation(["The current password is incorrect"])
    _check_password_strength(new)
    account.password_hash = _hasher.hash(new)
    account.must_change_password = False
    revoke_all_sessions(
        db,
        account,
        except_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
    )


def set_role(db: Session, account: Account, role: str, actor: Account) -> Account:
    if role not in ROLES:
        raise AuthRuleViolation(
            [f'role must be one of {", ".join(ROLES)}, not "{role}"']
        )
    if account.id == actor.id and role != "admin":
        raise AuthRuleViolation(
            ["An admin cannot demote their own account; another admin must."]
        )
    account.role = role
    db.commit()
    return account


def deactivate(db: Session, account: Account, actor: Account) -> Account:
    if account.id == actor.id:
        raise AuthRuleViolation(
            ["An admin cannot deactivate their own account; another admin must."]
        )
    if account.deactivated_at is None:
        account.is_active = False
        account.deactivated_at = _now()
        revoke_all_sessions(db, account)
    db.commit()
    return account


def reactivate(db: Session, account: Account) -> Account:
    account.is_active = True
    account.deactivated_at = None
    db.commit()
    return account
