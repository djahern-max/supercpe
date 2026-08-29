from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AuditExport(Base):
    """One generated audit bundle for one course (the 9.02.2 documentation
    set as a zip). Append-only and every export's zip is kept: an export is
    itself documentation of what the sponsor could produce on a date, and a
    later regeneration never alters an earlier one's stored bytes."""

    __tablename__ = "audit_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    generated_by_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    # sha256 of the stored zip bytes, so a produced copy can be verified
    # against the log.
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)

    course = relationship("Course")
    generated_by = relationship("Account")
