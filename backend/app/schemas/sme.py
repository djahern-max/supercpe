from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CredentialType = Literal["cpa", "tax_attorney", "enrolled_agent", "other"]
LicenseStatus = Literal["active", "inactive", "unknown"]


class SmeCreate(BaseModel):
    name: str = Field(min_length=1)
    credentials: str = ""
    credential_type: CredentialType
    license_jurisdiction: str = ""
    license_number: str = ""
    license_status: LicenseStatus = "unknown"
    email: str = ""
    notes: str = ""


class SmeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    credentials: str | None = None
    credential_type: CredentialType | None = None
    license_jurisdiction: str | None = None
    license_number: str | None = None
    license_status: LicenseStatus | None = None
    email: str | None = None
    notes: str | None = None


class SmeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    credentials: str
    credential_type: str
    license_jurisdiction: str
    license_number: str
    license_status: str
    email: str
    notes: str
    created_at: datetime
    updated_at: datetime
