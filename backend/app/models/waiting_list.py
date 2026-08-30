from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WaitingListEntry(Base):
    """A CPA who asked to hear when the course opens. Nothing more.

    These rows are NOT CPE records. No participant exists, no enrollment
    exists, nothing here supports a credit or a certificate, and
    `RETENTION_YEARS` does not apply. `removed_at` is a soft delete so a
    request to be taken off the list is honored immediately without
    deleting a row mid-migration; a removed row is excluded from every
    count, listing, and export. This is deliberately different from the
    9.02 accounts rule (deactivate, never delete, keep forever) — do not
    "fix" it for consistency: accounts anchor retained records, these
    rows anchor nothing.
    """

    __tablename__ = "waiting_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Lowercased and trimmed on write by services.waiting_list; unique on
    # the stored form.
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Two-letter code validated against US_JURISDICTIONS
    # (app/constants/jurisdictions.py — the list 020 will reuse).
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    firm: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # So 021 can tell an early signup from a later one.
    source: Mapped[str] = mapped_column(
        String, nullable=False, default="coming_soon", server_default="coming_soon"
    )

    __table_args__ = (
        CheckConstraint("state ~ '^[A-Z]{2}$'", name="ck_waiting_list_state_code"),
        CheckConstraint("email = lower(btrim(email))", name="ck_waiting_list_email_form"),
        # A reason only exists on a removed row.
        CheckConstraint(
            "removed_reason IS NULL OR removed_at IS NOT NULL",
            name="ck_waiting_list_reason_requires_removal",
        ),
    )
