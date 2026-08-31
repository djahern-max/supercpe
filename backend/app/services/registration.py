"""Self-registration and email verification (017).

The enumeration rule, inherited from 015's honeypot philosophy: every
well-formed registration or resend gets the identical 200 body
(CHECK_YOUR_EMAIL, one shared constant), whatever actually happened.
The branches differ only in which email goes out:

- unknown address    -> account created unverified + verification email
- active account     -> "you already have an account" email, no new row
- deactivated account -> "contact the sponsor" email; never reactivation.
  Reactivation is a deliberate human step (9.02 is why the row still
  exists), not a side effect of a form.

Malformed input (blank name, bad email shape, short password, unknown
jurisdiction) is refused 422 — the caller already knows what they typed,
so naming it reveals nothing about accounts.

Verification tokens are high-entropy random values stored as sha256, so
a fast cryptographic hash is correct here — argon2 is for passwords —
and lookup by hash equality is the same pattern sessions use. Expired,
unknown, superseded, and used tokens all fail with the same message.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.auth import (
    VERIFICATION_TOKEN_BYTES,
    VERIFICATION_TOKEN_HOURS,
)
from app.constants.jurisdictions import US_JURISDICTIONS
from app.models.account import Account, EmailVerificationToken
from app.services import auth as auth_service
from app.services import email as email_service
from app.services.auth import AuthRuleViolation
from app.services.sponsor import get_profile

# The one body every well-formed registration and resend answers with.
CHECK_YOUR_EMAIL = (
    "Check your email — the next step is on its way to the address you "
    "gave. If nothing arrives within a few minutes, look in your spam "
    "folder or use the resend link on the sign-in page."
)

# The one failure for an expired, unknown, superseded, or used token.
VERIFY_FAILED = (
    "That verification link is not valid. It may have expired or already "
    "been used — you can request a new one from the sign-in page."
)


class RegistrationRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _site_origin() -> str:
    # In prod CORS_ORIGINS is exactly https://supercpe.com (012 refuses
    # anything else at boot); in dev it is the Vite origin. Either way the
    # first origin is where the frontend lives, so links point there.
    return settings.cors_origins_list[0]


def _validate(
    db: Session, name: str, email: str, password: str, state: str
) -> None:
    errors = []
    if not name:
        errors.append("name is blank")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        errors.append(f'"{email}" is not an email address')
    if state and state not in US_JURISDICTIONS:
        errors.append(
            f'"{state}" is not a two-letter US licensing jurisdiction code'
        )
    try:
        # 002's password policy, verbatim — no second policy here.
        auth_service._check_password_strength(password)
    except AuthRuleViolation as violation:
        errors.extend(violation.errors)
    if errors:
        raise RegistrationRuleViolation(errors)


def register(
    db: Session, name: str, email: str, password: str, state: str = ""
) -> None:
    """One of the three branches above; the caller answers CHECK_YOUR_EMAIL
    regardless. Raises RegistrationRuleViolation only for malformed input."""
    name = name.strip()
    email = email.strip().lower()
    state = state.strip().upper()
    _validate(db, name, email, password, state)

    account = auth_service.get_account_by_email(db, email)
    if account is None:
        account = auth_service.create_account(
            db,
            email,
            "participant",
            password,
            created_by=None,
            display_name=name,
            must_change_password=False,
            email_verified=False,
            state=state or None,
        )
        _send_verification(db, account)
        return

    # The address is taken: hash anyway so the response costs the same as
    # the branch that stores a password, then email the address holder —
    # only they learn which case this was.
    auth_service._hasher.hash(password)
    if account.is_active:
        _send_already_registered(db, account)
    else:
        _send_contact_sponsor(db, account)


def resend(db: Session, email: str) -> None:
    """The resend affordance, same constant-response rule. An unknown
    address gets no email — there is no one to write to — and the same
    200 as everyone else."""
    email = email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise RegistrationRuleViolation(
            [f'"{email}" is not an email address']
        )
    account = auth_service.get_account_by_email(db, email)
    if account is None:
        return
    if not account.is_active:
        _send_contact_sponsor(db, account)
    elif account.email_verified_at is None:
        _send_verification(db, account)
    else:
        _send_already_registered(db, account)


def issue_token(db: Session, account: Account) -> str:
    """A fresh single-use token, superseding any live one — at most one
    token per account can ever verify. Returns the raw value for the
    email; only its sha256 is stored."""
    now = _now()
    for token in _live_tokens(db, account):
        token.superseded_at = now
    raw = secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)
    db.add(
        EmailVerificationToken(
            account_id=account.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=now + timedelta(hours=VERIFICATION_TOKEN_HOURS),
        )
    )
    db.commit()
    return raw


def token_is_valid(token: EmailVerificationToken, now: datetime) -> bool:
    """The one place token validity is derived: not used, not superseded,
    inside its 48 hours."""
    return (
        token.used_at is None
        and token.superseded_at is None
        and token.expires_at > now
    )


def verify(db: Session, raw_token: str) -> bool:
    """Consume the token and mark the account verified. False for every
    kind of bad token — the route shows VERIFY_FAILED without saying
    which kind."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash
        )
    )
    now = _now()
    if token is None or not token_is_valid(token, now):
        return False
    token.used_at = now
    token.account.email_verified_at = now
    db.commit()
    return True


def _live_tokens(
    db: Session, account: Account
) -> list[EmailVerificationToken]:
    now = _now()
    return [
        token
        for token in db.scalars(
            select(EmailVerificationToken).where(
                EmailVerificationToken.account_id == account.id
            )
        )
        if token_is_valid(token, now)
    ]


def _send_verification(db: Session, account: Account) -> None:
    raw = issue_token(db, account)
    sponsor = get_profile(db).name
    email_service.send(
        db,
        "verification",
        account.email,
        f"Verify your email address for {sponsor}",
        (
            f"Hello {account.display_name},\n\n"
            f"Follow this link to verify your email address:\n\n"
            f"{_site_origin()}/verify?token={raw}\n\n"
            f"The link works once and expires in "
            f"{VERIFICATION_TOKEN_HOURS} hours. If you did not create an "
            f"account, ignore this message and nothing will happen.\n\n"
            f"— {sponsor}"
        ),
    )


def _send_already_registered(db: Session, account: Account) -> None:
    sponsor = get_profile(db).name
    email_service.send(
        db,
        "already_registered",
        account.email,
        f"You already have a {sponsor} account",
        (
            f"Hello,\n\n"
            f"Someone — probably you — tried to register with this email "
            f"address, but it already has an account. You can sign in "
            f"at:\n\n{_site_origin()}/login\n\n"
            f"If this wasn't you, no action is needed; no new account was "
            f"created.\n\n— {sponsor}"
        ),
    )


def _send_contact_sponsor(db: Session, account: Account) -> None:
    profile = get_profile(db)
    contact = (
        f"write to {profile.contact_email}"
        if profile.contact_email
        else "reply to this message"
    )
    email_service.send(
        db,
        "contact_sponsor",
        account.email,
        f"About your {profile.name} account",
        (
            f"Hello,\n\n"
            f"This email address belongs to a deactivated account, and "
            f"registering again cannot reactivate it or create a new one. "
            f"To have the account restored, {contact}.\n\n"
            f"— {profile.name}"
        ),
    )
