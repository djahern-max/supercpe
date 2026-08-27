from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

COURSE_STATUSES = ("draft", "published")


class Course(Base):
    """The credit-bearing unit: an ordered set of lesson packages.

    `title` and `description` are typed by the admin. The four derived
    fields are copies of the value every attached package agrees on,
    re-copied on every attach and version update; the packages are the
    source and the admin cannot contradict them (3.01.1, 3.02.1)."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # 8.01.1 course announcement copy; required before publish (008).
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    field_of_study: Mapped[str | None] = mapped_column(String, nullable=True)
    knowledge_level: Mapped[str | None] = mapped_column(String, nullable=True)
    prerequisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    advance_preparation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft", server_default="draft"
    )
    # Bumped on every change a participant could observe, only ever by
    # services.courses.touch. Later features derive "credit is stale" and
    # "review is stale" from this one column.
    content_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # The stored result of services.credit.store (7.02.6 word count formula).
    # credit_breakdown holds the per-lesson inputs, one row per lesson in
    # position order: the 9.02.2(2)(ii) supporting documentation from which
    # the calculation can be reproduced line by line. Staleness is derived
    # (credit_computed_at vs content_updated_at, formula version vs the
    # constant), never stored.
    credit_award: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    credit_raw_minutes: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    credit_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_av_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_question_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_breakdown: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    credit_formula_version: Mapped[str | None] = mapped_column(String, nullable=True)
    credit_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    lessons: Mapped[list["CourseLesson"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseLesson.position",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published')", name="ck_courses_status"
        ),
    )


class CourseLesson(Base):
    __tablename__ = "course_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    course: Mapped[Course] = relationship(back_populates="lessons")
    package = relationship("LessonPackage")

    __table_args__ = (
        UniqueConstraint("course_id", "position", name="uq_course_lessons_position"),
        UniqueConstraint("course_id", "package_id", name="uq_course_lessons_package"),
        CheckConstraint("position >= 1", name="ck_course_lessons_position_positive"),
    )
