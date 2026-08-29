from datetime import datetime

from pydantic import BaseModel, Field


class PolicyCurrentOut(BaseModel):
    kind: str
    label: str
    body: str
    effective_at: datetime


class PoliciesPublicOut(BaseModel):
    """The public /policies payload: 8.01 items 8-10 as published, the
    re-take policy derived from the constants, and item 11 only while the
    sponsor may claim it (absent otherwise — never an empty claim)."""

    policies: list[PolicyCurrentOut]
    retake_policy: str
    sponsor_statement: str | None


class PolicyVersionOut(BaseModel):
    id: int
    kind: str
    body: str
    effective_at: datetime
    created_at: datetime
    created_by_email: str
    is_current: bool


class AdminPoliciesOut(BaseModel):
    history: list[PolicyVersionOut]
    missing: list[str]


class PolicyPublish(BaseModel):
    kind: str
    body: str = Field(min_length=1)
    # Defaults to now; a future date is not current until it arrives.
    effective_at: datetime | None = None


class HowItWorksOut(BaseModel):
    markdown: str
