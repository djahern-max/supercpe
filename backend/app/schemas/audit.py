from datetime import datetime

from pydantic import BaseModel


class AuditBundleRequest(BaseModel):
    # Videos are large; the admin UI says so beside the checkbox.
    include_video: bool = False


class AuditExportOut(BaseModel):
    id: int
    generated_at: datetime
    generated_by_email: str
    sha256: str
    size_bytes: int
    storage_key: str
