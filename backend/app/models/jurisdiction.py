from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class JurisdictionPolicy(Base):
    """One board of accountancy's credit rules as the admin verified them
    — reference data, not CPE records: nothing here enters a stored
    credit, a completion, or a certificate.

    Rows exist only for jurisdictions the admin has edited (create on
    edit); the table ships empty. Whether a row is displayable to
    participants is derived by `services.jurisdictions.displayable` from
    the increment, `source`, and `verified_on`, never stored — a row
    missing any of the three simply produces no hint (7.01: the claiming
    CPA keeps the duty to check with their board)."""

    __tablename__ = "jurisdiction_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # A US_JURISDICTIONS code; membership is validated at the service
    # layer, the shape here.
    jurisdiction: Mapped[str] = mapped_column(
        String(2), nullable=False, unique=True
    )
    # 7.01's acceptable increments, or `unknown` until verified.
    credit_increment: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown", server_default="unknown"
    )
    # Caps are per reporting period and depend on CPE superCPE cannot see,
    # so a cap is only ever quoted, never computed.
    non_technical_cap_note: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # Where the rule was read; required (with verified_on) to display.
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    verified_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Admin-only; never serialized toward a participant.
    notes: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "jurisdiction ~ '^[A-Z]{2}$'",
            name="ck_jurisdiction_policies_code",
        ),
        CheckConstraint(
            "credit_increment IN "
            "('one_fifth', 'one_half', 'whole', 'unknown')",
            name="ck_jurisdiction_policies_increment",
        ),
    )
