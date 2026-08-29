from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

POLICY_KINDS = ("registration", "refund", "complaint")


class PolicyVersion(Base):
    """One published version of one 8.01.1 policy: registration and
    attendance (item 8), refund and cancellation (item 9), or complaint
    resolution (item 10). Append-only — the current version of a kind is
    derived (`services.policies`: the latest `effective_at <= now()`),
    never marked; every version ever published stays readable, because a
    participant who enrolled under an old policy may hold the sponsor to
    it.

    The re-take policy is deliberately NOT a row: it is rendered from
    `RETAKES_ALLOWED` and `PASSING_PCT` so it can never disagree with what
    the code enforces. The 8.01 item 11 sponsor statement is a gated
    constant (`NASBA_SPONSOR_STATEMENT`), not a row, for the same reason."""

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # Markdown, rendered on the public /policies page and in the bundle.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )

    created_by = relationship("Account")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('registration', 'refund', 'complaint')",
            name="ck_policy_versions_kind",
        ),
    )
