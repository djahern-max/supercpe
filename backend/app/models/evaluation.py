from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.evaluation import SCALE_MAX, SCALE_MIN
from app.db import Base


class Evaluation(Base):
    """One participant's program evaluation (4.04.1), tied to the
    completion that made them eligible to give it. One per completion,
    ever; solicited, never required — a missing row means the participant
    declined, and nothing was withheld for it.

    `instructors_effective` (4.04.1 item 5) exists and is constrained to
    null: self study has no instructors, and the column being visibly null
    is the record answering item 5 as not applicable rather than omitting
    it. The prompt wording lives in `app/constants/evaluation.py` so the
    audit bundle can quote exactly what was asked. Never deleted."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    completion_id: Mapped[int] = mapped_column(
        ForeignKey("completions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    objectives_met: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prerequisites_appropriate: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )
    materials_relevant: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time_appropriate: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    instructors_effective: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    comments: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # The objectives the participant was rating, copied from the
    # completion's pinned packages at submit: the rating stays legible even
    # after the course's lessons change.
    objectives_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)

    completion = relationship("Completion")

    __table_args__ = tuple(
        CheckConstraint(
            f"{column} BETWEEN {SCALE_MIN} AND {SCALE_MAX}",
            name=f"ck_evaluations_{column}_scale",
        )
        for column in (
            "objectives_met",
            "prerequisites_appropriate",
            "materials_relevant",
            "time_appropriate",
        )
    ) + (
        # Item 5 is not applicable to self study; the column may never hold
        # a rating.
        CheckConstraint(
            "instructors_effective IS NULL",
            name="ck_evaluations_instructors_null",
        ),
    )


class EvaluationReview(Base):
    """One dated record that the sponsor reviewed a course's evaluation
    results (4.04.2). `summary_snapshot` is the summary as of
    `reviewed_at`; `informed_developer` is the admin's attestation that the
    developer of record was told (email is 018) — the bundle prints it as
    stated. Append-only: no update or delete path in code."""

    __tablename__ = "evaluation_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_by_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    summary_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    note: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    informed_developer: Mapped[bool] = mapped_column(Boolean, nullable=False)

    course = relationship("Course")
    reviewed_by = relationship("Account")
