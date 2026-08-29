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


class SiteModeChange(Base):
    """One flip of the sponsor profile's site_mode. Append-only: there is
    no update or delete path in code, so the log of who opened and closed
    the site survives any later state."""

    __tablename__ = "site_mode_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_mode: Mapped[str] = mapped_column(String, nullable=False)
    to_mode: Mapped[str] = mapped_column(String, nullable=False)
    changed_by_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    note: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )

    changed_by = relationship("Account")

    __table_args__ = (
        CheckConstraint(
            "from_mode IN ('coming_soon', 'open')",
            name="ck_site_mode_changes_from_mode",
        ),
        CheckConstraint(
            "to_mode IN ('coming_soon', 'open')",
            name="ck_site_mode_changes_to_mode",
        ),
    )
