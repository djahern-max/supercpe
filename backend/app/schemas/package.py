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
