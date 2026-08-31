from datetime import datetime

from pydantic import BaseModel


class LandingOut(BaseModel):
    """What the coming-soon page needs to render, and nothing else.

    Deliberately no field for course facts, credit figures, objectives,
    or prices: 8.01's eleven-item disclosure is 016's job, and a payload
    that cannot carry those facts cannot half-disclose them.
    """

    sponsor_name: str
    may_claim_registry: bool
    policies_published: bool


class WaitingListRequest(BaseModel):
    name: str
    email: str
    state: str
    firm: str = ""
    # Honeypot: hidden and empty in the real form. A non-empty value is
    # answered with the same 200 as a real signup and stores nothing.
    website: str = ""


class WaitingListJoined(BaseModel):
    """The one signup response body — identical for a first submission,
    a repeat, and a tripped honeypot, so nothing about the reply says
    whether a row exists."""

    message: str


class WaitingListEntryOut(BaseModel):
    id: int
    name: str
    email: str
    state: str
    firm: str | None
    created_at: datetime
    source: str
    # 021: the one promised invitation — null until attempted, then
    # sent/failed with the attempt time.
    invited_at: datetime | None
    invitation_status: str | None


class WaitingListAdminOut(BaseModel):
    total: int
    entries: list[WaitingListEntryOut]
    # 021: the Invitations panel's counts, over active entries only.
    invited: int
    failed: int
    invitable: int


class WaitingListRemoveRequest(BaseModel):
    reason: str = ""


class InvitationRunOut(BaseModel):
    """One Send run's summary. attempted = sent + failed; skipped rows
    were already successfully invited and are never attempted again."""

    attempted: int
    sent: int
    failed: int
    skipped_already_invited: int
