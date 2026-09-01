from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.fields_of_study import FIELDS_OF_STUDY
from app.constants.knowledge_levels import KNOWLEDGE_LEVELS
from app.constants.package_kinds import (
    COUNTED_ROLE,
    KIND_TEXT,
    KIND_VIDEO,
    PACKAGE_KINDS,
    SECTION_ROLES,
    WORD_COUNT_SOURCES,
)
from app.db import Base


def _quoted_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


class LessonPackage(Base):
    __tablename__ = "lesson_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 023: "video" (the program is the narrated video) or "text" (the
    # program is the study guide in `sections`, videos supplement it).
    # Server-defaulted so every row ingested before 023 reads as video.
    kind: Mapped[str] = mapped_column(
        String, nullable=False, default=KIND_VIDEO, server_default=KIND_VIDEO
    )
    lesson_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # For a video package, the ffprobe-measured length of video.mp4. For
    # a text package, the sum of its supplemental media durations, each
    # ffprobe-measured at ingestion — so the column means the same thing
    # either way: this lesson's actual audio/video duration time (7.02.7).
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_source: Mapped[str] = mapped_column(String, nullable=False)
    # The video manifest's measured_at; null for text packages, whose
    # durations are measured here at ingestion, not declared.
    measured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    narration_blocks: Mapped[int] = mapped_column(Integer, nullable=False)
    # Video: the manifest's declared count, trusted. Text: the sum of the
    # `body` sections' counted words, computed here from the shipped
    # markdown (7.02.5). `word_count_source` records which, and prints in
    # the 9.02.2(2)(ii) calculation record.
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count_source: Mapped[str] = mapped_column(
        String, nullable=False, default="manifest", server_default="manifest"
    )
    av_is_additional_learning: Mapped[bool] = mapped_column(Boolean, nullable=False)
    field_of_study: Mapped[str] = mapped_column(String, nullable=False)
    knowledge_level: Mapped[str] = mapped_column(String, nullable=False)
    prerequisites: Mapped[str] = mapped_column(Text, nullable=False)
    advance_preparation: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Both are the video package's; a text package has neither, and its
    # program materials are its sections and media rows.
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_key: Mapped[str | None] = mapped_column(String, nullable=True)
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

    @property
    def is_text(self) -> bool:
        return self.kind == KIND_TEXT

    @property
    def body_sections(self) -> list["PackageSection"]:
        """The sections whose words 7.02.5 counts, in reading order."""
        return [s for s in self.sections if s.role == COUNTED_ROLE]

    sections: Mapped[list["PackageSection"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="PackageSection.position",
    )
    media: Mapped[list["PackageMedia"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="PackageMedia.position",
    )
    glossary_terms: Mapped[list["GlossaryTerm"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="GlossaryTerm.position",
    )

    __table_args__ = (
        UniqueConstraint("lesson_id", "version", name="uq_lesson_packages_lesson_id_version"),
        CheckConstraint(
            f"kind IN ({_quoted_list(PACKAGE_KINDS)})",
            name="ck_lesson_packages_kind",
        ),
        CheckConstraint(
            f"word_count_source IN ({_quoted_list(WORD_COUNT_SOURCES)})",
            name="ck_lesson_packages_word_count_source",
        ),
        # A video package has a video and a transcript of it; a text
        # package has neither, and cannot acquire one by accident.
        CheckConstraint(
            f"(kind = '{KIND_VIDEO}') = (video_key IS NOT NULL)",
            name="ck_lesson_packages_video_key_iff_video",
        ),
        CheckConstraint(
            f"(kind = '{KIND_VIDEO}') = (transcript IS NOT NULL)",
            name="ck_lesson_packages_transcript_iff_video",
        ),
        CheckConstraint(
            f"(kind = '{KIND_VIDEO}') = (measured_at IS NOT NULL)",
            name="ck_lesson_packages_measured_at_iff_video",
        ),
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


class PackageSection(Base):
    """One section of a text package's study guide, normalized from the
    manifest and the shipped markdown at ingest.

    `role` is what makes 7.02.5's exclusions structural: only `body`
    sections' words reach the credit formula. `word_count` is this
    section's own count either way — an excluded section's real size is
    worth showing a reviewer — and the package's `word_count` sums the
    `body` rows alone.
    """

    __tablename__ = "package_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The manifest's section `id`, e.g. "sec-01"; unique within the package.
    section_key: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Order within the manifest's `sections` — the order the reader serves.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Path inside the package zip, retained so the stored row can be traced
    # back to the file the author wrote.
    file: Mapped[str] = mapped_column(String, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    package: Mapped["LessonPackage"] = relationship(back_populates="sections")

    @property
    def counted(self) -> bool:
        """Whether this section's words entered the formula (7.02.5)."""
        return self.role == COUNTED_ROLE

    __table_args__ = (
        UniqueConstraint(
            "package_id", "section_key", name="uq_package_sections_key"
        ),
        UniqueConstraint(
            "package_id", "position", name="uq_package_sections_position"
        ),
        CheckConstraint(
            f"role IN ({_quoted_list(SECTION_ROLES)})",
            name="ck_package_sections_role",
        ),
        CheckConstraint(
            "word_count >= 0",
            name="ck_package_sections_word_count_non_negative",
        ),
    )


class PackageMedia(Base):
    """One supplemental video of a text package, placed after a section.

    `av_is_additional_learning` is true on every row by CHECK, not by
    convention: 7.02.7 admits audio/video duration into the formula only
    when the segment is "not narration of the text", and a text package's
    media minutes always count, so a row that did not make the claim could
    not lawfully be in the term. The contract refuses the export; this
    refuses the storage.
    """

    __tablename__ = "package_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The manifest's media `id`, e.g. "vid-01"; unique within the package.
    media_key: Mapped[str] = mapped_column(String, nullable=False)
    file: Mapped[str] = mapped_column(String, nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    # ffprobe-measured at ingestion, never typed (7.02.7).
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    # The section key this clip renders after.
    after_section: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    av_is_additional_learning: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )

    package: Mapped["LessonPackage"] = relationship(back_populates="media")

    __table_args__ = (
        UniqueConstraint("package_id", "media_key", name="uq_package_media_key"),
        UniqueConstraint(
            "package_id", "position", name="uq_package_media_position"
        ),
        CheckConstraint(
            "duration_seconds > 0", name="ck_package_media_duration_positive"
        ),
        CheckConstraint(
            "av_is_additional_learning",
            name="ck_package_media_additional_learning",
        ),
    )


class GlossaryTerm(Base):
    """One key term and its definition (4.05.3 item 3).

    4.05.3 requires instructional materials to include "the definition of
    key terms (for example, a glossary or a search function that takes a
    participant to the definition of a key word)". These rows are both:
    the course glossary page and the in-reader lookup read from here.
    """

    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    term: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    # The section the term is defined in, normally the glossary section.
    section_key: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    package: Mapped["LessonPackage"] = relationship(
        back_populates="glossary_terms"
    )

    __table_args__ = (
        UniqueConstraint("package_id", "term", name="uq_glossary_terms_term"),
        UniqueConstraint(
            "package_id", "position", name="uq_glossary_terms_position"
        ),
    )
