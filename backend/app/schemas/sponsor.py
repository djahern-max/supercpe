from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.sponsor import REGISTRY_STATUSES


class StateRegistration(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: str = Field(pattern=r"^[A-Za-z]{2}$")
    registration_number: str = Field(min_length=1)
    notes: str = ""

    @field_validator("state")
    @classmethod
    def uppercase_state(cls, value: str) -> str:
        return value.upper()


class SponsorProfileUpdate(BaseModel):
    """A full replacement of the editable fields; PUT sends them all."""

    name: str
    legal_name: str
    registry_status: str
    national_registry_id: str
    website: str
    contact_email: str
    contact_phone: str
    address: str
    other_certificate_statements: str

    @field_validator("registry_status")
    @classmethod
    def known_status(cls, value: str) -> str:
        if value not in REGISTRY_STATUSES:
            raise ValueError(f"registry_status must be one of {REGISTRY_STATUSES}")
        return value


class SponsorFinding(BaseModel):
    """A sponsor-level readiness finding (readiness.sponsor_findings),
    shown beside the launch-readiness panel on /admin/sponsor."""

    code: str
    level: str
    message: str


class SponsorProfileAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    legal_name: str
    registry_status: str
    national_registry_id: str
    website: str
    contact_email: str
    contact_phone: str
    address: str
    other_certificate_statements: str
    updated_at: datetime
    missing_fields: list[str]
    missing_for_issuance: list[str]
    may_claim_registry: bool
    state_registrations: list[StateRegistration]
    findings: list[SponsorFinding]
    # 011: what stands between the sponsor and opening the site
    # (readiness.launch_findings) — missing policies block the flip;
    # evaluation_review_due warns beside them.
    launch_findings: list[SponsorFinding]


class SponsorProfilePublic(BaseModel):
    """The non-sensitive subset. `national_registry_id` is present only when
    the sponsor may claim Registry membership; the router serializes with
    exclude_none so an unregistered profile never carries the field.

    027: `contact_email` joins it so the site footer and the exhausted
    re-takes notice can say where to write. The route is already behind
    `require_site_open_or_session`, and the same address already goes to
    every registrant (017's contact-sponsor email) and to Stripe as the
    checkout support email (018)."""

    name: str
    website: str
    contact_email: str = ""
    national_registry_id: str | None = None
