from pydantic import BaseModel


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    # Optional state of licensure; strangers are not made to hand it over
    # to get an account (020 will want it when it matters).
    state: str = ""


class ResendRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    token: str


class RegisteredOut(BaseModel):
    """The one constant body for every well-formed registration and
    resend — the response never says whether the email is known."""

    message: str


class VerifiedOut(BaseModel):
    message: str


class TestEmailOut(BaseModel):
    backend: str
    recipient: str
