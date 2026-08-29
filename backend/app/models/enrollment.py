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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ENROLLMENT_SOURCES = ("admin", "purchase")


class Enrollment(Base):
    """The record everything hangs off: one participant's right to take one
    course, carrying the 9.02.2(3) expiration date from creation. 017 later
    creates these on a successful charge; nothing downstream changes.

    `status` (active / expired / completed) is derived by
    `services.enrollments.status` from `expires_at` and the completion row,
    never stored. `package_versions` pins `{package_id: version}` as of
    enrollment; the player and assessment serve the pinned versions until
    the enrollment completes or expires. Never deleted."""

    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # enrolled_at + ENROLLMENT_DAYS, computed in the service and stored: a
    # fact about the enrollment (9.02.2(3)), not derived state.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    package_versions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    account = relationship("Account", foreign_keys=[account_id])
    course = relationship("Course")
    completion: Mapped["Completion | None"] = relationship(
        back_populates="enrollment", uselist=False
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('admin', 'purchase')", name="ck_enrollments_source"
        ),
        # "One active enrollment per (account, course)" depends on now(), so
        # it cannot be a partial index; the service enforces it. This plain
        # index serves that lookup.
        Index("ix_enrollments_account_course", "account_id", "course_id"),
    )


class LessonProgress(Base):
    """The furthest point watched in one pinned lesson, per enrollment.
    Monotonic: the service never lowers it."""

    __tablename__ = "lesson_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="RESTRICT"), nullable=False
    )
    furthest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "package_id", name="uq_lesson_progress_lesson"
        ),
        CheckConstraint(
            "furthest_seconds >= 0",
            name="ck_lesson_progress_furthest_non_negative",
        ),
    )


class ReviewAnswer(Base):
    """One review-question answer per enrollment — the 5.01.2 engagement
    record. A re-answer updates the row and `answered_at`; `is_correct`
    snapshots the verdict at grading. `question_id` deliberately has no
    ON DELETE, like `attempt_answers`: a package version whose questions
    were answered cannot be deleted out from under the record."""

    __tablename__ = "review_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), nullable=False
    )
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    question = relationship("Question")

    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "question_id", name="uq_review_answers_question"
        ),
    )


class Completion(Base):
    """One row per passed enrollment: the 9.02.2(1) completion record and
    the 9.01 certificate, frozen. `certificate_snapshot` copies every
    certificate-bearing fact at completion time; nothing in it is ever
    re-read from the live tables, so no later edit to the course, the
    sponsor, or the account can change what the participant earned.

    Immutable: no update path except `certificate_key` and
    `certificate_rendered_at` being set once at the first render; no delete
    path, ever."""

    __tablename__ = "completions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("attempts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    # The passing attempt's submitted_at (9.02.2(1) course completion date).
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    credit_awarded: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    field_of_study: Mapped[str] = mapped_column(String, nullable=False)
    # YYYY-NNNNNN from the per-year sequence.
    certificate_number: Mapped[str] = mapped_column(
        String, nullable=False, unique=True
    )
    # 32 random bytes as hex; 018's public verification page looks it up.
    verification_token: Mapped[str] = mapped_column(
        String, nullable=False, unique=True
    )
    certificate_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Storage key of the first rendered PDF; null until rendered.
    certificate_key: Mapped[str | None] = mapped_column(String, nullable=True)
    certificate_rendered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    enrollment: Mapped[Enrollment] = relationship(back_populates="completion")
    attempt = relationship("Attempt")


class CertificateSequence(Base):
    """The per-year counter behind certificate numbers. Read with a row
    lock inside the completion transaction so two simultaneous passes can
    never mint the same number; the unique constraint on
    `certificate_number` is the backstop."""

    __tablename__ = "certificate_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)
