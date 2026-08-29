from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ATTEMPT_STATUSES = ("open", "passed", "failed")


class Attempt(Base):
    """One sitting of a course's qualified assessment (6.01.2), retained
    whatever its outcome: attempts are the raw material of the 9.02.2(1)
    completion-verification record.

    An attempt carries exactly one identity: an enrollment (a participant's
    real sitting, 010) or an opaque `preview_id` the admin frontend
    generates per session (007's preview path, which stays for admins and
    reviewers)."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=True
    )
    preview_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Snapshot of the threshold the attempt was graded against, so the
    # record stays provable if the constant ever changes.
    passing_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # [{package_id, version}] in lesson order at start, so the attempt can
    # prove exactly which questions were asked even after a re-export swaps
    # the course to newer package versions (9.02.2(1)).
    package_versions: Mapped[list] = mapped_column(JSONB, nullable=False)

    answers: Mapped[list["AttemptAnswer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    course = relationship("Course")
    enrollment = relationship("Enrollment")

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'passed', 'failed')", name="ck_attempts_status"
        ),
        # A preview attempt is exactly one with a preview identity.
        CheckConstraint(
            "is_preview = (preview_id IS NOT NULL)",
            name="ck_attempts_preview_id_iff_preview",
        ),
        # Every attempt carries exactly one identity: enrollment or preview.
        CheckConstraint(
            "(enrollment_id IS NULL) != (preview_id IS NULL)",
            name="ck_attempts_enrollment_xor_preview",
        ),
        # Only one open attempt per identity at a time.
        Index(
            "uq_attempts_one_open_per_preview",
            "course_id",
            "preview_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index(
            "uq_attempts_one_open_per_enrollment",
            "enrollment_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


class AttemptAnswer(Base):
    """One answer of an attempt. `is_correct` is null while the attempt is
    open and written at grading; it is never returned to the client for a
    failed attempt (6.01.2 sub-ii). `question_id` deliberately has no
    ON DELETE: a package version whose questions were asked on an attempt
    cannot be deleted out from under the record."""

    __tablename__ = "attempt_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), nullable=False
    )
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"), nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    attempt: Mapped[Attempt] = relationship(back_populates="answers")
    question = relationship("Question")
    choice = relationship("Choice")

    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "question_id", name="uq_attempt_answers_question"
        ),
    )
