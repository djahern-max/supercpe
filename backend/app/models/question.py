from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Question(Base):
    """One question of a package version, normalized from its questions.json
    at ingest. Questions belong to the package version, not the course: a
    course's review questions are those of its attached packages' current
    versions."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The package's `id` field, e.g. "q-01"; unique within the package.
    question_key: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # Where a review question is placed. Exactly one of these is set on
    # a review question and neither on an assessment question: a video
    # package places by 1-based index into manifest.video.blocks, a text
    # package (023) by the key of the section the question follows. Both
    # answer the same 5.01.2.1 requirement — questions "placed throughout
    # the program in sufficient intervals" — in the two media.
    after_block: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_section: Mapped[str | None] = mapped_column(String, nullable=True)
    # Order within the package's questions.json.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    # Learning objective ids from the package manifest.
    objective_keys: Mapped[list] = mapped_column(JSONB, nullable=False)

    choices: Mapped[list["Choice"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Choice.position",
    )

    __table_args__ = (
        UniqueConstraint(
            "package_id", "question_key", name="uq_questions_package_id_question_key"
        ),
        CheckConstraint(
            "kind IN ('review', 'assessment')", name="ck_questions_kind"
        ),
        # A review question carries exactly one placement; an assessment
        # question carries none. Review questions pause the program after
        # a block or a section; assessments never do.
        CheckConstraint(
            "(kind = 'review') = "
            "(after_block IS NOT NULL OR after_section IS NOT NULL)",
            name="ck_questions_placement_iff_review",
        ),
        CheckConstraint(
            "NOT (after_block IS NOT NULL AND after_section IS NOT NULL)",
            name="ck_questions_one_placement",
        ),
    )


class Choice(Base):
    __tablename__ = "choices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The package's choice `id`, e.g. "a"; unique within the question.
    choice_key: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Exactly one per question, enforced by the normalizer and by test;
    # never serialized to the player (the answer key stays server-side).
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped[Question] = relationship(back_populates="choices")

    __table_args__ = (
        UniqueConstraint(
            "question_id", "choice_key", name="uq_choices_question_id_choice_key"
        ),
    )
