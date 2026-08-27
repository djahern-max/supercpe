from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

CREDENTIAL_TYPES = ("cpa", "tax_attorney", "enrolled_agent", "other")
LICENSE_STATUSES = ("active", "inactive", "unknown")


class SubjectMatterExpert(Base):
    """A person who was qualified in a subject matter on a date (4.01.1,
    4.02.1). Deliberately not tied to any accounts table, now or in 009: an
    account is a login and has a different lifetime. License claims are
    recorded as stated (9.02.2(4)); superCPE does not verify them against
    any state board."""

    __tablename__ = "subject_matter_experts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Free text as it should print, e.g. "CPA" or "CPA, MST".
    credentials: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    # The 4.02 participation rule reads this, not the free text.
    credential_type: Mapped[str] = mapped_column(String, nullable=False)
    license_jurisdiction: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    license_number: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    license_status: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown", server_default="unknown"
    )
    email: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
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
            "credential_type IN ('cpa', 'tax_attorney', 'enrolled_agent', 'other')",
            name="ck_smes_credential_type",
        ),
        CheckConstraint(
            "license_status IN ('active', 'inactive', 'unknown')",
            name="ck_smes_license_status",
        ),
    )
