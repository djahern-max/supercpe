from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.assessment import AssessmentInfo
from app.schemas.player import PlayLesson


class MyAssessmentInfo(AssessmentInfo):
    """The assessment as the enrolled participant sees it: the pinned
    questions, plus availability and the sittings left."""

    retakes_remaining: int
    available: bool
    unavailable_reasons: list[str]


class MyCompletionOut(BaseModel):
    """The completion as the participant sees it. `certificate_ready` is
    false only while the sponsor's issuance fields still block the render;
    the completion itself is already recorded either way."""

    completion_id: int
    completed_at: datetime
    credit_awarded: str
    field_of_study: str
    certificate_number: str
    certificate_ready: bool
    # 4.04.1: whether the evaluation prompt should still be shown —
    # solicited, never required; false once submitted or after
    # SOLICIT_UNTIL_DAYS.
    evaluation_requested: bool


class MyLessonProgress(BaseModel):
    package_id: int
    lesson_id: str
    version: int
    position: int
    title: str
    duration_seconds: int
    furthest_seconds: int
    review_answered: int
    review_total: int


class MyEnrollmentSummary(BaseModel):
    enrollment_id: int
    course_code: str
    title: str
    status: str
    enrolled_at: datetime
    expires_at: datetime
    credit: str | None
    field_of_study: str | None
    lessons_total: int
    lessons_watched: int
    review_answered: int
    review_total: int
    assessment_available: bool
    retakes_remaining: int
    failed_attempts: int
    open_attempt_id: int | None
    completion: MyCompletionOut | None


class MyEnrollmentDetail(MyEnrollmentSummary):
    """The 8.01 course facts the participant enrolled on, plus per-lesson
    progress from the pinned packages."""

    description: str
    knowledge_level: str | None
    prerequisites: str | None
    advance_preparation: str | None
    lessons: list[MyLessonProgress]
    assessment_unavailable_reasons: list[str]


class MyPlayLesson(PlayLesson):
    furthest_seconds: int


class ProgressUpdate(BaseModel):
    furthest_seconds: int = Field(ge=0)


class ProgressOut(BaseModel):
    package_id: int
    furthest_seconds: int


class EnrollRequest(BaseModel):
    """Admin enrollment: the email of an existing participant account."""

    email: str


class AdminEnrollmentOut(BaseModel):
    id: int
    email: str
    display_name: str
    status: str
    source: str
    enrolled_at: datetime
    expires_at: datetime
    package_versions: dict
    lessons_total: int
    lessons_watched: int
    review_answered: int
    review_total: int
    failed_attempts: int
    has_completion: bool


class AdminCompletionOut(BaseModel):
    id: int
    enrollment_id: int
    email: str
    participant_name: str
    completed_at: datetime
    credit_awarded: str
    field_of_study: str
    certificate_number: str
    certificate_rendered_at: datetime | None
    certificate_ready: bool
    overdue: bool
    # 9.02: completed_at + RETENTION_YEARS, derived, never stored.
    retain_until: datetime
