from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.certificate import (
    CERTIFICATE_SPONSOR_FIELDS,
    ISSUANCE_SPONSOR_FIELDS,
)
from app.db import Base

REGISTRY_STATUSES = ("not_registered", "registered")


class SponsorProfile(Base):
    """The one sponsor this application serves. The CHECK on id makes a
    second row impossible; the migration inserts the row itself."""

    __tablename__ = "sponsor_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    # The entity 9.01.1 holds responsible for awarding the credits; may
    # equal `name`.
    legal_name: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    registry_status: Mapped[str] = mapped_column(
        String, nullable=False, default="not_registered", server_default="not_registered"
    )
    national_registry_id: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    website: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    contact_email: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    contact_phone: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    address: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    # 9.01 item 11: any other statements required by boards of accountancy,
    # one statement per line. Empty is normal.
    other_certificate_statements: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # Phase B gate: while `coming_soon`, public routes and pages 404 for
    # anyone without a session. A logged setting here, not an environment
    # variable, so it flips without a deploy; every change writes a
    # `site_mode_changes` row (services.site.set_site_mode).
    site_mode: Mapped[str] = mapped_column(
        String, nullable=False, default="coming_soon", server_default="coming_soon"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_sponsor_profile_singleton"),
        CheckConstraint(
            "registry_status IN ('not_registered', 'registered')",
            name="ck_sponsor_profile_registry_status",
        ),
        # A sponsor that has not been accepted onto the National Registry
        # does not have a sponsor ID and may not claim one.
        CheckConstraint(
            "registry_status = 'registered' OR national_registry_id = ''",
            name="ck_sponsor_profile_registry_id_requires_registered",
        ),
        CheckConstraint(
            "site_mode IN ('coming_soon', 'open')",
            name="ck_sponsor_profile_site_mode",
        ),
    )

    @property
    def may_claim_registry(self) -> bool:
        """The single boolean every later feature reads before rendering
        the words "National Registry" or a sponsor ID anywhere."""
        return self.registry_status == "registered" and self.national_registry_id != ""

    def missing_fields(self, for_issuance: bool = False) -> list[str]:
        """Names of the sponsor facts still blank.

        The default view is 003's launch-readiness list: everything a fully
        credentialed certificate names, Registry membership included. The
        `for_issuance` view is what actually gates issuing a certificate
        (010): a sponsor that is not on the Registry may still issue one —
        it simply cannot print item 8, which gates on `may_claim_registry`
        at completion instead — and Phase B's NASBA application needs a
        sample certificate before membership exists."""
        if for_issuance:
            return [
                field
                for field in ISSUANCE_SPONSOR_FIELDS
                if getattr(self, field) == ""
            ]
        missing = [
            field for field in CERTIFICATE_SPONSOR_FIELDS if getattr(self, field) == ""
        ]
        if self.registry_status == "not_registered":
            missing.append("registry_status")
        return missing


class SponsorStateRegistration(Base):
    """A sponsor registration the sponsor actually holds with one state
    board (9.01 item 9). superCPE does not encode which states require
    what; certificates will print whatever is stored here."""

    __tablename__ = "sponsor_state_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    registration_number: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
