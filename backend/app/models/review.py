from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

REVIEW_DECISIONS = ("approved", "changes_requested")


class CourseReview(Base):
    """One recorded content review (4.02), of the course content as it
    stood at a moment. Immutable once recorded: there is no update path in
    code, and corrections are new reviews. Whether a review is *current* is
    derived by `services.development.current_review` from the timestamps,
    never stored (9.02.2(4) keeps the record either way)."""

    __tablename__ = "course_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("subject_matter_experts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewed_at: Mapped[date] = mapped_column(Date, nullable=False)
    # The course's content_updated_at at the moment the review was recorded:
    # the review is of *that* content, and a later content change supersedes
    # it (4.02 requires review again after each significant revision).
    content_updated_at_reviewed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # 4.02.1's rare case: why review before first presentation was
    # impractical. Documented and reported, never used to bypass anything.
    impractical_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    course = relationship("Course", back_populates="reviews")
    reviewer = relationship("SubjectMatterExpert")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'changes_requested')",
            name="ck_course_reviews_decision",
        ),
    )
