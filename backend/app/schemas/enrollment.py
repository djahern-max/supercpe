from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.assessment import AssessmentInfo
from app.schemas.player import PlayLesson


class MyAssessmentInfo(AssessmentInfo):
    """The assessment as the enrolled participant sees it: the pinned
    questions, plus availability and the sittings left."""

    # 028: None under the unlimited policy.
    retakes_remaining: int | None
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
    # 019: the code printed on the certificate, so the participant can
    # hand a board the /certificates/verify link instead of the PDF.
    verification_code: str
    # 4.04.1: whether the evaluation prompt should still be shown —
    # solicited, never required; false once submitted or after
    # SOLICIT_UNTIL_DAYS.
    evaluation_requested: bool


class MyLessonProgress(BaseModel):
    package_id: int
    lesson_id: str
    # 023: "video" or "text" — which surface opens this lesson, a player
    # or a reader.
    kind: str
    version: int
    position: int
    title: str
    duration_seconds: int
    furthest_seconds: int
    review_answered: int
    review_total: int
    # 023c: watched (video) or read (text) — see `lesson_done`.
    done: bool


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
    # 023c: was `lessons_watched`, which counted a text lesson from the
    # start. Now the lessons watched (video) or read (text), and
    # `lessons_kind` says which word applies: "video", "text", or "mixed".
    lessons_done: int
    lessons_kind: str
    review_answered: int
    review_total: int
    assessment_available: bool
    # 028: None under the unlimited policy; `retakes_unlimited` beside it.
    retakes_remaining: int | None
    retakes_unlimited: bool
    failed_attempts: int
    open_attempt_id: int | None
    completion: MyCompletionOut | None
    # 028: true only on an expired enrollment the participant may renew at
    # no charge (paid, never completed, this is the most recent one) —
    # derived from payment and enrollment rows, never stored.
    renewable: bool


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
    lessons_done: int
    lessons_kind: str
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
    # 019: pending | sent | failed — failed is the loud flag the Resend
    # button answers.
    delivery_status: str
    delivered_at: datetime | None
    # 9.02: completed_at + RETENTION_YEARS, derived, never stored.
    retain_until: datetime
