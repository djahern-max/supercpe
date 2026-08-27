import secrets

from fastapi import Header, HTTPException

from app.config import settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if x_admin_token is None or not secrets.compare_digest(
        x_admin_token, settings.admin_token
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
