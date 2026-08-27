from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.fields_of_study import FIELDS_OF_STUDY
from app.constants.knowledge_levels import KNOWLEDGE_LEVELS
from app.db import Base


def _quoted_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


class LessonPackage(Base):
    __tablename__ = "lesson_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_source: Mapped[str] = mapped_column(String, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    narration_blocks: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    av_is_additional_learning: Mapped[bool] = mapped_column(Boolean, nullable=False)
    field_of_study: Mapped[str] = mapped_column(String, nullable=False)
    knowledge_level: Mapped[str] = mapped_column(String, nullable=False)
    prerequisites: Mapped[str] = mapped_column(Text, nullable=False)
    advance_preparation: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    video_key: Mapped[str] = mapped_column(String, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Both live in the manifest, not columns: packages ingested before the
    # course_code contract rule have neither, and None is the honest answer.
    @property
    def course_code(self) -> str | None:
        return self.manifest.get("course_code")

    @property
    def manifest_position(self) -> int | None:
        return self.manifest.get("position")

    # Packages ingested before the video.blocks contract rule (video-tool 03)
    # have none; they are fixtures and None is the honest answer.
    @property
    def blocks(self) -> list | None:
        return self.manifest.get("video", {}).get("blocks")

    __table_args__ = (
        UniqueConstraint("lesson_id", "version", name="uq_lesson_packages_lesson_id_version"),
        # 7.02.7: the column can never hold anything but a measured duration,
        # even if the validator is bypassed.
        CheckConstraint(
            "duration_source = 'measured'",
            name="ck_lesson_packages_duration_source_measured",
        ),
        CheckConstraint(
            f"field_of_study IN ({_quoted_list(FIELDS_OF_STUDY)})",
            name="ck_lesson_packages_field_of_study",
        ),
        CheckConstraint(
            f"knowledge_level IN ({_quoted_list(KNOWLEDGE_LEVELS)})",
            name="ck_lesson_packages_knowledge_level",
        ),
    )
