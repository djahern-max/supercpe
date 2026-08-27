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
    may_claim_registry: bool
    state_registrations: list[StateRegistration]


class SponsorProfilePublic(BaseModel):
    """The non-sensitive subset. `national_registry_id` is present only when
    the sponsor may claim Registry membership; the router serializes with
    exclude_none so an unregistered profile never carries the field."""

    name: str
    website: str
    national_registry_id: str | None = None
