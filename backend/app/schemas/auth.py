from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ROLE = Literal["participant", "reviewer", "admin"]


class LoginRequest(BaseModel):
    email: str
    password: str


class MeOut(BaseModel):
    id: int
    email: str
    role: str
    display_name: str
    must_change_password: bool
    # 029: whether a participant holds a current subscription, derived
    # on every read (never stored); false for every other role. The site
    # header's Subscribe link and the course page's enroll section key
    # on it. A fact about the viewer's own account, nothing about a course.
    subscription_current: bool = False
    # 030: how this account can sign in — "password" when a hash is
    # stored, "google" when a Google account is linked. Derived per
    # read from the row; the account page renders it.
    signin_methods: list[str] = []


class GoogleSignInRequest(BaseModel):
    # The ID token Google Identity Services handed the browser (030).
    credential: str


class GoogleConfigOut(BaseModel):
    """What the browser needs to render Google's button, and nothing
    else: the client id, or null when the feature is not configured."""

    client_id: str | None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MyStateOut(BaseModel):
    state: str | None


class MyStateRequest(BaseModel):
    # A US_JURISDICTIONS code, or null/"" to clear — the participant's
    # claim about themselves, not a credential (020).
    state: str | None = None


class AccountCreate(BaseModel):
    email: str
    role: ROLE
    display_name: str = ""


class AccountCreated(BaseModel):
    """The only response that ever carries the initial password; it is not
    stored in clear and never appears again."""

    id: int
    email: str
    role: str
    display_name: str
    initial_password: str


class AccountOut(BaseModel):
    id: int
    email: str
    role: str
    display_name: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    deactivated_at: datetime | None
    last_sign_in: datetime | None
    open_sessions: int


class RoleRequest(BaseModel):
    role: ROLE


class SiteOut(BaseModel):
    site_mode: str
    sponsor_name: str


class SiteModeRequest(BaseModel):
    site_mode: Literal["coming_soon", "open"]
    note: str = ""


class SiteModeChangeOut(BaseModel):
    id: int
    from_mode: str
    to_mode: str
    changed_by_email: str
    changed_at: datetime
    note: str
