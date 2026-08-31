from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EmailMessage(Base):
    """One outbound email: what kind, to whom, when, and which backend
    handled it. The body is NOT stored — a verification link at rest
    belongs only in the token table, hashed.

    These rows are operational records, not CPE records — the same
    declaration as 015's waiting list, and the same reasoning: no
    participant linkage requirement, nothing here supports a credit or a
    certificate, and `RETENTION_YEARS` does not apply.
    """

    __tablename__ = "email_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # verification | already_registered | contact_sponsor | test, and
    # whatever kinds 019/021 add; a name, not an enum, on purpose.
    kind: Mapped[str] = mapped_column(String, nullable=False)
    recipient: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    backend: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "backend IN ('console', 'smtp')",
            name="ck_email_message_backend",
        ),
    )
