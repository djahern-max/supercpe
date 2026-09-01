from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PackageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
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


class PackageSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_key: str
    role: str
    title: str
    position: int
    file: str
    word_count: int
    # Whether these words entered the credit formula (7.02.5). False for
    # front matter, glossary, and appendix sections — the material the
    # paragraph names as not critical to the learning objectives.
    counted: bool


class PackageMediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_key: str
    file: str
    storage_key: str
    duration_seconds: int
    after_section: str
    av_is_additional_learning: bool


class GlossaryTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    term: str
    definition: str
    section_key: str | None


class SectionRoleCount(BaseModel):
    role: str
    label: str
    sections: int
    words: int
    counted: bool


class PackageOverview(BaseModel):
    """The human summary the admin package view renders above the raw
    manifest.

    It exists because a walkthrough found that the one number a reviewer
    most needs — how many words this lesson contributes to the credit
    formula, and from where — was visible only by reading raw JSON. Every
    field here is derived from the stored row; nothing is stored twice."""

    kind: str
    # "computed" (from the shipped body text, 7.02.5) or "manifest"
    # (declared by the exporter and taken on trust).
    word_count_source: str
    word_count: int
    total_words: int
    sections_by_role: list[SectionRoleCount]
    media_count: int
    media_seconds: int
    review_questions: int
    assessment_questions: int


class PackageDetail(PackageSummary):
    content_hash: str
    duration_source: str
    measured_at: datetime | None
    narration_blocks: int
    word_count: int
    word_count_source: str
    av_is_additional_learning: bool
    prerequisites: str
    advance_preparation: str
    video_key: str | None
    manifest: dict
    questions: list
    # Filled in by the router from `packages.overview`; derived on
    # read, never stored.
    overview: PackageOverview | None = None
    sections: list[PackageSectionOut] = []
    media: list[PackageMediaOut] = []
    glossary_terms: list[GlossaryTermOut] = []


class IngestResponse(BaseModel):
    package: PackageDetail
    created: bool
    # Non-fatal findings from validation — today, a text package with no
    # glossary terms. The package is kept; the publish gate is where the
    # ones that matter become refusals.
    warnings: list[str] = []


class ValidationErrors(BaseModel):
    errors: list[str]
