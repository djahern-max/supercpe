from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    course_code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None


class AttachRequest(BaseModel):
    package_id: int
    position: int | None = None


class MoveRequest(BaseModel):
    direction: Literal["up", "down"]


class UpdateVersionRequest(BaseModel):
    new_package_id: int


class DeveloperRequest(BaseModel):
    sme_id: int
    used_technology: bool


class ReviewCreate(BaseModel):
    reviewer_id: int
    reviewed_at: date
    decision: Literal["approved", "changes_requested"]
    notes: str = ""
    impractical_basis: str | None = None


class ReviewCycleRequest(BaseModel):
    review_cycle: Literal["annual", "biennial"]


class CourseReviewOut(BaseModel):
    id: int
    reviewer_id: int
    reviewer_name: str
    reviewer_credentials: str
    reviewed_at: date
    content_updated_at_reviewed: datetime
    decision: str
    notes: str
    impractical_basis: str | None
    recorded_by: str
    created_at: datetime
    # Derived against the course's content_updated_at, never stored.
    is_current: bool
    is_superseded: bool


class CourseDevelopmentAdmin(BaseModel):
    """The 4.01/4.01.1/4.02 facts as the admin course page shows them."""

    developer_id: int | None
    developer_name: str | None
    developer_credentials: str | None
    developer_used_technology: bool
    review_cycle: str
    published_at: datetime | None
    unpublished_at: datetime | None
    review_due_at: date | None
    last_documented_date: date | None
    reviews: list[CourseReviewOut]


class LessonObjective(BaseModel):
    id: str
    text: str


class ObjectiveGroup(BaseModel):
    lesson_id: str
    package_id: int
    position: int
    objectives: list[LessonObjective]


class CourseLessonItem(BaseModel):
    package_id: int
    lesson_id: str
    version: int
    position: int
    title: str
    duration_seconds: int
    # Set when a newer ingested version of this lesson exists, so the admin
    # can offer "update to vN".
    newer_package_id: int | None = None
    newer_version: int | None = None


class CreditLessonRowOut(BaseModel):
    """One line of the stored 9.02.2(2)(ii) breakdown."""

    lesson_id: str
    package_id: int
    version: int
    position: int
    title: str
    duration_seconds: int
    av_is_additional_learning: bool
    av_seconds_counted: int
    word_count: int
    words_counted: int
    review_questions: int
    assessment_questions: int


class CourseCreditAdmin(BaseModel):
    """The stored credit measurement, term by term. Decimal values are
    serialized as strings ("0.4") so no consumer ever re-parses them as
    floats. All measurement fields are null until the first compute."""

    is_stale: bool
    stale_reason: str | None
    computed_at: datetime | None
    formula_version: str | None
    award: str | None
    raw_minutes: str | None
    raw_credit: str | None
    word_count: int | None
    av_seconds: int | None
    question_count: int | None
    word_minutes: str | None
    av_minutes: str | None
    question_minutes: str | None
    rows: list[CreditLessonRowOut]
    as_text: str | None


class ReadinessFinding(BaseModel):
    code: str
    level: Literal["block", "warn"]
    message: str


class ReviewCountsOut(BaseModel):
    """5.01.2.1 count vs requirement, shown even when satisfied. `required`
    is null while the credit is stale."""

    counting: int
    required: int | None


class AdminQuestion(BaseModel):
    """A question as the admin question view lists it. Deliberately carries
    no choice texts and no answer key; the stored `correct` never reaches a
    payload outside grading responses."""

    question_key: str
    kind: str
    after_block: int | None
    position: int
    stem: str
    choice_count: int
    # False for review questions with only two choices, which exist but do
    # not count toward the 5.01.2.1 minimum (and for assessment questions,
    # which never count toward it).
    counts_toward_minimum: bool


class QuestionGroup(BaseModel):
    """One lesson's questions, review and assessment listed separately."""

    lesson_id: str
    package_id: int
    position: int
    review: list[AdminQuestion]
    assessment: list[AdminQuestion]


class CourseSummaryAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_code: str
    title: str
    status: str
    lesson_count: int
    content_updated_at: datetime
    credit_award: str | None
    credit_is_stale: bool


class CourseDetailAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_code: str
    title: str
    description: str
    field_of_study: str | None
    knowledge_level: str | None
    prerequisites: str | None
    advance_preparation: str | None
    status: str
    content_updated_at: datetime
    created_at: datetime
    updated_at: datetime
    lessons: list[CourseLessonItem]
    objectives: list[ObjectiveGroup]
    credit: CourseCreditAdmin
    questions: list[QuestionGroup]
    readiness: list[ReadinessFinding]
    review_counts: ReviewCountsOut
    development: CourseDevelopmentAdmin
    # 010: enrollments whose derived status is active right now; the admin
    # page quotes it beside unpublish and delete.
    active_enrollment_count: int


class PublicLesson(BaseModel):
    lesson_id: str
    position: int
    title: str
    duration_seconds: int


class PublicObjectiveGroup(BaseModel):
    lesson_id: str
    position: int
    objectives: list[LessonObjective]


class PublicPerson(BaseModel):
    """A developer or reviewer as disclosed publicly: name and credentials
    only, never a license number (those stay in 9.02.2(4) records)."""

    name: str
    credentials: str


class CoursePublicSummary(BaseModel):
    """8.01 disclosure facts for the catalog list."""

    course_code: str
    title: str
    description: str
    field_of_study: str | None
    knowledge_level: str | None
    prerequisites: str | None
    advance_preparation: str | None
    lesson_count: int
    total_duration_seconds: int
    # 8.01 item 3: the recommended CPE credit, with the basis it rests on.
    # Both are null while the stored credit is stale or below the minimum
    # awardable; a participant is never shown a stale number or "0.0".
    recommended_credit: str | None
    credit_basis: str | None
    # 4.01/4.01.1/4.02 provenance, and the 4.01 "most recent publication,
    # revision, or review date" disclosure.
    developed_by: PublicPerson | None
    reviewed_by: PublicPerson | None
    last_reviewed: date | None
    last_documented_date: date | None


class CoursePublicDetail(CoursePublicSummary):
    """The full 8.01 disclosure payload for a published course page."""

    objectives: list[PublicObjectiveGroup]
    lessons: list[PublicLesson]
