from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Account(Base):
    """A person who can sign in: the identity 6.01 completion verification
    and the 9.02.2(1) "by individual participant" records hang on.

    There is no delete path, only deactivation: a deleted account would
    orphan the records 9.02 requires kept for five years. Not an SME —
    008 decided there is no FK between the two, ever; a reviewer's account
    is their login, their SME record is their qualification (4.02.1)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Lowercased on write by services.auth; unique on the stored form.
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # When the address was proven reachable (017). Admin-created accounts
    # get it at creation — the admin hand-delivering the initial password
    # is the vouch; self-registered accounts get it when the emailed token
    # is consumed, and cannot log in while it is null.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # State of licensure, optional at self-registration (017); the codes
    # 020's per-jurisdiction credit policy will key on. Null for accounts
    # that never gave one.
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    failed_logins: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Null for the CLI-created first admin; otherwise the admin who created
    # this account.
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="account"
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('participant', 'reviewer', 'admin')",
            name="ck_accounts_role",
        ),
        CheckConstraint(
            "state IS NULL OR state ~ '^[A-Z]{2}$'",
            name="ck_accounts_state_code",
        ),
    )


class AuthSession(Base):
    """One server-side login session. The raw token exists only in the
    HttpOnly cookie; the row stores its sha256. Whether a session is valid
    is derived by `services.auth.session_is_valid` from `revoked_at`,
    `expires_at`, and `last_seen_at`, never stored as a boolean."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    ip: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )

    account: Mapped[Account] = relationship(back_populates="sessions")


class EmailVerificationToken(Base):
    """One emailed verification link (017). The raw token exists only in
    the email; the row stores its sha256, like sessions. Whether a token
    is usable is derived by `services.registration.token_is_valid` from
    `used_at`, `superseded_at`, and `expires_at`, never stored — a resend
    supersedes the prior token, consuming marks `used_at`, so there is at
    most one live token per account without a flag that can drift.
    Written so 017a's password reset can reuse the shape unchanged."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account: Mapped[Account] = relationship()

    __table_args__ = (
        # A token leaves the live state exactly one way.
        CheckConstraint(
            "used_at IS NULL OR superseded_at IS NULL",
            name="ck_email_verification_tokens_one_ending",
        ),
    )
