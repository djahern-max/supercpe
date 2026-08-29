"""Payloads for the reviewer surface. Read-only course facts plus what the
record-review form needs; deliberately no readiness findings, credit
breakdown, or attempt data — those are admin views."""

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.course import CourseReviewOut


class ReviewCourseSummary(BaseModel):
    course_code: str
    title: str
    status: str
    # "current" | "superseded" | "none", derived by the same logic that
    # gates publish.
    review_standing: str
    last_reviewed: date | None


class ReviewLesson(BaseModel):
    package_id: int
    position: int
    title: str
    duration_seconds: int


class ReviewSme(BaseModel):
    """Just enough to name the reviewer of record in the form; the full
    SME record (license details) stays an admin view."""

    id: int
    name: str
    credentials: str


class ReviewCourseDetail(BaseModel):
    course_code: str
    title: str
    description: str
    field_of_study: str | None
    knowledge_level: str | None
    status: str
    content_updated_at: datetime
    review_standing: str
    last_reviewed: date | None
    lessons: list[ReviewLesson]
    reviews: list[CourseReviewOut]
    smes: list[ReviewSme]
