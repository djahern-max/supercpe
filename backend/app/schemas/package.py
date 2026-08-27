from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PackageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: str
    version: int
    title: str
    duration_seconds: int
    field_of_study: str
    knowledge_level: str
    ingested_at: datetime
    # From the manifest; None on packages ingested before the contract
    # required a course_code.
    course_code: str | None = None
    # Course code of the attaching course; set by list_packages only.
    attached_to: str | None = None


class PackageDetail(PackageSummary):
    content_hash: str
    duration_source: str
    measured_at: datetime
    narration_blocks: int
    word_count: int
    av_is_additional_learning: bool
    prerequisites: str
    advance_preparation: str
    video_key: str
    manifest: dict
    questions: list


class IngestResponse(BaseModel):
    package: PackageDetail
    created: bool


class ValidationErrors(BaseModel):
    errors: list[str]
