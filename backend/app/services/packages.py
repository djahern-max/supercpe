"""Validate and ingest lesson packages per docs/course-package.md.

`validate` runs every contract rule against a package zip and either returns
a ValidatedPackage or the full list of failure messages. It touches no
database and no storage. `ingest` handles idempotency and versioning and is
the only writer.
"""

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.fields_of_study import FIELDS_OF_STUDY
from app.constants.package_kinds import (
    COUNTED_ROLE,
    DEFAULT_KIND,
    KIND_TEXT,
    KIND_VIDEO,
    PACKAGE_KINDS,
    ROLE_LABELS,
    SECTION_ROLES,
    WORD_COUNT_COMPUTED,
    WORD_COUNT_MANIFEST,
)
from app.constants.question_minimums import MIN_CHOICES_ASSESSMENT
from app.constants.knowledge_levels import (
    KNOWLEDGE_LEVELS,
    LEVELS_REQUIRING_PREREQUISITES,
    PREREQUISITES_NONE,
)
from app.models.course import CourseLesson
from app.models.lesson_package import (
    GlossaryTerm,
    LessonPackage,
    PackageMedia,
    PackageSection,
)
from app.services import ffprobe
from app.services import questions as questions_service
from app.services import word_count as word_count_service
from app.services.courses import CourseRuleViolation
from app.storage import Storage

PACKAGE_FILES = ("manifest.json", "video.mp4", "transcript.md", "questions.json")

# A text package's two root files; everything else it carries lives under
# one of the two directories the contract names.
TEXT_ROOT_FILES = ("manifest.json", "questions.json")
GUIDE_DIR = "guide/"
MEDIA_DIR = "media/"

# Contract fields and their JSON types. bool is checked before int because
# True is an int in Python.
MANIFEST_FIELDS = {
    "package_version": int,
    "lesson_id": str,
    "course_code": str,
    "position": int,
    "title": str,
    "content_hash": str,
    "video": dict,
    "learning_objectives": list,
    "field_of_study": str,
    "knowledge_level": str,
    "prerequisites": str,
    "advance_preparation": str,
    "sources": list,
    "author": dict,
    "word_count": int,
    "av_is_additional_learning": bool,
}
VIDEO_FIELDS = {
    "duration_seconds": int,
    "duration_source": str,
    "measured_at": str,
    "narration_blocks": int,
    "tts_provider": str,
    "tts_voice_id": str,
    "tts_model": str,
    "blocks": list,
}
AUTHOR_FIELDS = {
    "name": str,
    "credentials": str,
    "license_jurisdiction": str,
    "license_number": str,
}

DURATION_TOLERANCE_SECONDS = Decimal(1)

REVIEW_MIN_CHOICES = 2
# The 6.01.2 forced-choice floor; aliased so ingest refusals and the
# readiness finding can never disagree.
ASSESSMENT_MIN_CHOICES = MIN_CHOICES_ASSESSMENT


@dataclass
class SectionSpec:
    """One validated guide section, ready to become a `PackageSection`."""

    section_key: str
    role: str
    title: str
    position: int
    file: str
    markdown: str
    word_count: int


@dataclass
class MediaSpec:
    """One validated supplemental clip, with its ffprobe-measured length."""

    media_key: str
    file: str
    path: Path
    duration_seconds: int
    after_section: str
    position: int
    av_is_additional_learning: bool


@dataclass
class ValidatedPackage:
    lesson_id: str
    title: str
    content_hash: str
    duration_seconds: int
    duration_source: str
    measured_at: datetime | None
    narration_blocks: int
    word_count: int
    av_is_additional_learning: bool
    field_of_study: str
    knowledge_level: str
    prerequisites: str
    advance_preparation: str
    manifest: dict
    questions: list
    # Everything below is defaulted so a video package is built exactly as
    # it was before 023; only a text package fills the text fields in.
    transcript: str | None = None
    video_path: Path | None = None
    kind: str = KIND_VIDEO
    word_count_source: str = WORD_COUNT_MANIFEST
    sections: list[SectionSpec] = field(default_factory=list)
    media: list[MediaSpec] = field(default_factory=list)
    glossary_terms: list[dict] = field(default_factory=list)
    # Non-fatal findings. Ingestion reports them and proceeds; the publish
    # gate is where the ones that matter become refusals (B7), because a
    # package worth keeping is worth keeping even while a course built on
    # it is not yet publishable.
    warnings: list[str] = field(default_factory=list)


def _has_type(value, typ) -> bool:
    if typ is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, typ)


def _check_fields(obj: dict, fields: dict, prefix: str, errors: list[str]) -> bool:
    ok = True
    for name, typ in fields.items():
        if name not in obj:
            errors.append(f"{prefix}.{name}: missing required field")
            ok = False
        elif not _has_type(obj[name], typ):
            errors.append(
                f"{prefix}.{name}: expected {typ.__name__},"
                f" got {type(obj[name]).__name__}"
            )
            ok = False
    return ok


def compute_content_hash(transcript: bytes, questions: bytes, video: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(transcript)
    digest.update(questions)
    digest.update(video)
    return digest.hexdigest()


def compute_text_content_hash(
    sections: list[bytes], questions: bytes, media: list[bytes]
) -> str:
    """The text package's hash: every section file in manifest order, then
    questions.json, then every media file in manifest order. Same role as
    the video package's hash — a re-upload with the same digest is a
    no-op, a different one is a new lesson version that makes the course's
    credit and review stale."""
    digest = hashlib.sha256()
    for chunk in sections:
        digest.update(chunk)
    digest.update(questions)
    for chunk in media:
        digest.update(chunk)
    return digest.hexdigest()


def _peek_kind(zf: zipfile.ZipFile, top: str, inner: set[str]) -> str:
    """The manifest's `kind`, or the contract's default when it cannot be
    read. Never reports an error of its own: whatever is wrong with an
    unreadable manifest is reported by the validator for the kind this
    returns."""
    if "manifest.json" not in inner:
        return DEFAULT_KIND
    try:
        manifest = json.loads(zf.read(f"{top}/manifest.json"))
    except (KeyError, ValueError):
        return DEFAULT_KIND
    if not isinstance(manifest, dict):
        return DEFAULT_KIND
    kind = manifest.get("kind", DEFAULT_KIND)
    return kind if kind in PACKAGE_KINDS else DEFAULT_KIND


def _text_layout_errors(top: str, inner: set[str]) -> list[str]:
    """The text package's zip layout: two root files, markdown under
    guide/, media under media/, nothing else."""
    errors = []
    for name in TEXT_ROOT_FILES:
        if name not in inner:
            errors.append(f"package: missing required file {top}/{name}")
    stray = sorted(
        name
        for name in inner
        if name not in TEXT_ROOT_FILES
        and not name.startswith((GUIDE_DIR, MEDIA_DIR))
    )
    for name in stray:
        errors.append(
            f"package: unexpected file {top}/{name}; a text package's files "
            f"live in {GUIDE_DIR} and {MEDIA_DIR}"
        )
    if not any(
        name.startswith(GUIDE_DIR) and name.endswith(".md") for name in inner
    ):
        errors.append(
            f"package: a text package needs at least one markdown file in "
            f"{top}/{GUIDE_DIR}; the guide is the program"
        )
    return errors


def validate(zip_path: Path) -> ValidatedPackage | list[str]:
    errors: list[str] = []

    # Rule 1: zip structure.
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        return ["package: not a valid zip file"]

    with zf:
        names = [n for n in zf.namelist() if not n.startswith("__MACOSX/")]
        top_levels = {n.split("/", 1)[0] for n in names}
        loose_files = sorted(n for n in names if "/" not in n)
        if loose_files:
            errors.append(
                "package: files at the zip root are not allowed; the zip must "
                f"contain exactly one top-level directory (found {', '.join(loose_files)})"
            )
        if len(top_levels) != 1:
            errors.append(
                "package: expected exactly one top-level directory, "
                f"found {len(top_levels)}: {', '.join(sorted(top_levels))}"
            )
        if errors:
            return errors

        top = top_levels.pop()
        inner = {
            n.split("/", 1)[1]
            for n in names
            if "/" in n and n.split("/", 1)[1]
        }
        # The manifest names its own kind, so the layout rules cannot be
        # chosen until it has been read. A manifest that is missing or
        # unreadable peeks as `video`, which is also the contract's
        # default for an absent `kind` — so a broken package still gets
        # the video package's refusals, word for word, rather than a
        # confusing complaint about a text layout it never claimed.
        kind = _peek_kind(zf, top, inner)
        if kind == KIND_TEXT:
            errors += _text_layout_errors(top, inner)
        else:
            missing = [f for f in PACKAGE_FILES if f not in inner]
            extra = sorted(inner - set(PACKAGE_FILES))
            for f in missing:
                errors.append(f"package: missing required file {top}/{f}")
            for f in extra:
                errors.append(f"package: unexpected file {top}/{f}")
        if errors:
            return errors

        extract_dir = zip_path.parent / "extracted"
        zf.extractall(extract_dir)
        package_dir = extract_dir / top

    if kind == KIND_TEXT:
        return _validate_text(package_dir, inner)
    return _validate_video(package_dir)

def _validate_identity(manifest: dict, errors: list[str]) -> None:
    """Rule 2: the package version and where the lesson belongs.

    Shared by both kinds — a text package is placed into a course by the
    same `course_code` and `position` a video package is."""
    version = manifest.get("package_version")
    if _has_type(version, int) and version != 1:
        errors.append(f"manifest.package_version: expected 1, received {version}")

    if _has_type(manifest.get("course_code"), str) and not manifest["course_code"].strip():
        errors.append("manifest.course_code: must be a non-blank string")
    if _has_type(manifest.get("position"), int) and manifest["position"] < 1:
        errors.append(
            f"manifest.position: must be a positive integer, got {manifest['position']}"
        )


def _validate_descriptors(
    manifest: dict, errors: list[str]
) -> tuple[str, str, str, str, set[str]]:
    """Rules 8-12: the facts 3.01.1, 3.02.1, and 8.01 make a participant
    able to read before enrolling, plus the learning objectives every
    question must map to. Identical for both package kinds — what a
    program is about does not depend on whether it is read or watched.
    """
    # Rule 8.
    field_of_study = manifest.get("field_of_study")
    if _has_type(field_of_study, str) and field_of_study not in FIELDS_OF_STUDY:
        errors.append(
            f'manifest.field_of_study: "{field_of_study}" is not a NASBA field '
            "of study (docs/2024-Fields-of-Study.pdf)"
        )

    # Rule 9.
    knowledge_level = manifest.get("knowledge_level")
    if _has_type(knowledge_level, str) and knowledge_level not in KNOWLEDGE_LEVELS:
        errors.append(
            f'manifest.knowledge_level: "{knowledge_level}" is not one of '
            f"{', '.join(KNOWLEDGE_LEVELS)} (3.01.1)"
        )

    # Rule 10: prerequisites and advance preparation per 3.02.1.
    prerequisites = manifest.get("prerequisites")
    advance_preparation = manifest.get("advance_preparation")
    if knowledge_level in LEVELS_REQUIRING_PREREQUISITES:
        for name, value in (
            ("prerequisites", prerequisites),
            ("advance_preparation", advance_preparation),
        ):
            if _has_type(value, str) and not value.strip():
                errors.append(
                    f"manifest.{name}: must be stated for {knowledge_level} "
                    "programs (3.02.1)"
                )
    else:
        if _has_type(prerequisites, str) and not prerequisites.strip():
            prerequisites = PREREQUISITES_NONE
        if _has_type(advance_preparation, str) and not advance_preparation.strip():
            advance_preparation = PREREQUISITES_NONE

    # Rule 11: learning objectives.
    objective_ids: set[str] = set()
    objectives = manifest.get("learning_objectives")
    if isinstance(objectives, list):
        if not objectives:
            errors.append("manifest.learning_objectives: must not be empty")
        for i, obj in enumerate(objectives):
            label = f"manifest.learning_objectives[{i}]"
            if not isinstance(obj, dict):
                errors.append(f"{label}: expected an object with id and text")
                continue
            obj_id = obj.get("id")
            if not isinstance(obj_id, str) or not obj_id.strip():
                errors.append(f"{label}.id: must be a non-blank string")
            elif obj_id in objective_ids:
                errors.append(f'{label}.id: duplicate objective id "{obj_id}"')
            else:
                objective_ids.add(obj_id)
            text = obj.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{label}.text: must be a non-blank string")

    # Rule 12.
    sources = manifest.get("sources")
    if isinstance(sources, list) and not sources:
        errors.append(
            "manifest.sources: must not be empty; a lesson with no cited "
            "authority is not a CPE lesson"
        )

    return (
        field_of_study,
        knowledge_level,
        prerequisites,
        advance_preparation,
        objective_ids,
    )


def _validate_video(package_dir: Path) -> ValidatedPackage | list[str]:
    """Everything downstream of the zip layout for a video package.

    Unchanged by 023, down to the wording of every refusal: a manifest
    with no `kind` is a video package and ingests exactly as it did."""
    errors: list[str] = []

    transcript_bytes = (package_dir / "transcript.md").read_bytes()
    questions_bytes = (package_dir / "questions.json").read_bytes()
    video_path = package_dir / "video.mp4"

    try:
        transcript = transcript_bytes.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("transcript.md: not valid UTF-8")
    try:
        manifest = json.loads((package_dir / "manifest.json").read_bytes())
        if not isinstance(manifest, dict):
            errors.append("manifest.json: must be a JSON object")
            manifest = None
    except json.JSONDecodeError as exc:
        errors.append(f"manifest.json: not valid JSON ({exc.msg} at line {exc.lineno})")
        manifest = None
    try:
        questions = json.loads(questions_bytes)
        if not isinstance(questions, list):
            errors.append("questions.json: must be a JSON array")
            questions = None
    except json.JSONDecodeError as exc:
        errors.append(f"questions.json: not valid JSON ({exc.msg} at line {exc.lineno})")
        questions = None
    if errors:
        return errors

    # Rule 3: required fields with correct types.
    _check_fields(manifest, MANIFEST_FIELDS, "manifest", errors)
    video = manifest.get("video")
    video_ok = isinstance(video, dict) and _check_fields(
        video, VIDEO_FIELDS, "manifest.video", errors
    )
    if isinstance(manifest.get("author"), dict):
        _check_fields(manifest["author"], AUTHOR_FIELDS, "manifest.author", errors)

    _validate_identity(manifest, errors)

    measured_at = None
    if video_ok:
        # Rule 4: measured durations only.
        if video["duration_source"] != "measured":
            errors.append(
                f'manifest.video.duration_source: "{video["duration_source"]}" is '
                "refused; 7.02.7 credits actual audio/video duration time, so "
                "estimated durations are refused. video-tool must export with "
                "measured audio."
            )
        # Rule 5: manifest duration matches the uploaded file.
        try:
            measured = ffprobe.duration_seconds(video_path)
            declared = Decimal(video["duration_seconds"])
            if abs(declared - measured) > DURATION_TOLERANCE_SECONDS:
                errors.append(
                    f"manifest.video.duration_seconds: manifest declares "
                    f"{declared} seconds but ffprobe measured {measured} seconds; "
                    "they must agree within 1 second"
                )
        except ValueError as exc:
            errors.append(f"video.mp4: {exc}")
        try:
            measured_at = datetime.fromisoformat(video["measured_at"])
            if measured_at.tzinfo is None:
                errors.append(
                    "manifest.video.measured_at: timestamp must include a timezone offset"
                )
        except ValueError:
            errors.append(
                "manifest.video.measured_at: not an ISO 8601 timestamp, "
                f"got {video['measured_at']!r}"
            )
        if _has_type(video.get("narration_blocks"), int) and video["narration_blocks"] < 1:
            errors.append(
                f"manifest.video.narration_blocks: must be at least 1, "
                f"got {video['narration_blocks']}"
            )
        # Rule 18: measured block timings, so review questions can be placed
        # throughout the program at measured points (5.01.2.1). One entry per
        # narrated block, in playback order, ids matching transcript.md's
        # `## <block id>` headings, contiguous, ending at duration_seconds
        # within 1 second. "Values come from measured audio" is an attestation
        # carried by duration_source (rule 4); what is checkable here is the
        # structure. The first entry's start being the title sheet's duration
        # is video-tool's obligation and is not checkable from the package.
        if isinstance(video.get("blocks"), list):
            _validate_blocks(video, transcript, errors)

    # Rule 6: content hash over transcript + questions + video bytes, in order.
    computed_hash = compute_content_hash(
        transcript_bytes, questions_bytes, video_path.read_bytes()
    )
    declared_hash = manifest.get("content_hash")
    if _has_type(declared_hash, str) and declared_hash.lower() != computed_hash:
        errors.append(
            "manifest.content_hash: does not match sha256 over transcript.md + "
            f"questions.json + video.mp4 bytes; manifest says {declared_hash}, "
            f"computed {computed_hash}. Package contents changed after export."
        )

    # Rule 7.
    word_count = manifest.get("word_count")
    if _has_type(word_count, int) and word_count < 0:
        errors.append(f"manifest.word_count: must be >= 0, got {word_count}")

    (
        field_of_study,
        knowledge_level,
        prerequisites,
        advance_preparation,
        objective_ids,
    ) = _validate_descriptors(manifest, errors)

    # Rules 13-17: questions.
    if questions is not None:
        _validate_questions(questions, objective_ids, video, errors)

    if errors:
        return errors

    return ValidatedPackage(
        lesson_id=manifest["lesson_id"],
        title=manifest["title"],
        content_hash=computed_hash,
        duration_seconds=video["duration_seconds"],
        duration_source=video["duration_source"],
        measured_at=measured_at,
        narration_blocks=video["narration_blocks"],
        word_count=word_count,
        av_is_additional_learning=manifest["av_is_additional_learning"],
        field_of_study=field_of_study,
        knowledge_level=knowledge_level,
        prerequisites=prerequisites,
        advance_preparation=advance_preparation,
        manifest=manifest,
        questions=questions,
        transcript=transcript,
        video_path=video_path,
    )


TEXT_MANIFEST_FIELDS = {
    "package_version": int,
    "kind": str,
    "lesson_id": str,
    "course_code": str,
    "position": int,
    "title": str,
    "content_hash": str,
    "learning_objectives": list,
    "field_of_study": str,
    "knowledge_level": str,
    "prerequisites": str,
    "advance_preparation": str,
    "sources": list,
    "author": dict,
    "sections": list,
    "glossary_terms": list,
}
SECTION_FIELDS = {"id": str, "file": str, "role": str, "title": str}
MEDIA_FIELDS = {"id": str, "file": str, "placement": dict}
GLOSSARY_FIELDS = {"term": str, "definition": str}

# 7.02.7's test, quoted into every refusal that turns on it so an author
# never has to go looking for why the export was rejected.
ADDITIONAL_LEARNING_SENTENCE = (
    "7.02.7 admits audio/video duration into the credit formula only when "
    "the segment constitutes additional learning for the participant, that "
    "is, not narration of the text. If the video reads the guide aloud it "
    "does not belong in a text package."
)


def _validate_text(package_dir: Path, inner: set[str]) -> ValidatedPackage | list[str]:
    """Everything downstream of the zip layout for a text package (023).

    The one structural difference from the video path: `word_count` is not
    read, it is computed. 7.02.5 counts "the text of the required reading",
    and here superCPE has that text, so it counts the words itself from
    the `body` sections and records that it did. Nothing about the number
    depends on the exporter's honesty; only the assignment of a section to
    a role does, and that is what the 4.02 reviewer signs.
    """
    errors: list[str] = []
    warnings: list[str] = []

    questions_bytes = (package_dir / "questions.json").read_bytes()
    try:
        manifest = json.loads((package_dir / "manifest.json").read_bytes())
        if not isinstance(manifest, dict):
            errors.append("manifest.json: must be a JSON object")
            manifest = None
    except json.JSONDecodeError as exc:
        errors.append(f"manifest.json: not valid JSON ({exc.msg} at line {exc.lineno})")
        manifest = None
    try:
        questions = json.loads(questions_bytes)
        if not isinstance(questions, list):
            errors.append("questions.json: must be a JSON array")
            questions = None
    except json.JSONDecodeError as exc:
        errors.append(f"questions.json: not valid JSON ({exc.msg} at line {exc.lineno})")
        questions = None
    if errors:
        return errors

    _check_fields(manifest, TEXT_MANIFEST_FIELDS, "manifest", errors)
    if isinstance(manifest.get("author"), dict):
        _check_fields(manifest["author"], AUTHOR_FIELDS, "manifest.author", errors)
    if "media" in manifest and not isinstance(manifest["media"], list):
        errors.append(
            "manifest.media: expected list, got "
            f"{type(manifest['media']).__name__}"
        )
        manifest["media"] = []

    # 7.02.5, structurally: superCPE counts the shipped body text, so a
    # declared count could only ever contradict it.
    if "word_count" in manifest:
        errors.append(
            "manifest.word_count: text packages must not declare a word "
            "count; superCPE computes it from the body sections' markdown "
            "(7.02.5). Remove the field."
        )
    if "av_is_additional_learning" in manifest:
        errors.append(
            "manifest.av_is_additional_learning: belongs on each media "
            "item in a text package, not on the manifest"
        )
    if "video" in manifest:
        errors.append(
            "manifest.video: a text package has no video.mp4; supplemental "
            f"clips are listed in manifest.media and live in {MEDIA_DIR}"
        )

    _validate_identity(manifest, errors)
    (
        field_of_study,
        knowledge_level,
        prerequisites,
        advance_preparation,
        objective_ids,
    ) = _validate_descriptors(manifest, errors)

    sections, section_bytes = _validate_sections(
        manifest, package_dir, inner, errors
    )
    section_keys = {section.section_key for section in sections}
    media, media_bytes = _validate_media(
        manifest, package_dir, inner, section_keys, errors
    )
    _validate_glossary(manifest, section_keys, errors, warnings)

    if questions is not None:
        _validate_questions(
            questions, objective_ids, None, errors, section_keys=section_keys
        )

    # Every file in the zip is named by the manifest: an unlisted markdown
    # file is either forgotten reading or a section quietly dropped from
    # the count, and neither should ingest silently.
    named = {section.file for section in sections} | {m.file for m in media}
    orphans = sorted(
        name
        for name in inner
        if name.startswith((GUIDE_DIR, MEDIA_DIR))
        and not name.endswith("/")
        and name not in named
    )
    for name in orphans:
        errors.append(
            f"package: {name} is in the zip but not listed in the manifest; "
            "every guide and media file must be named by a section or a "
            "media item"
        )

    computed_hash = compute_text_content_hash(
        section_bytes, questions_bytes, media_bytes
    )
    declared_hash = manifest.get("content_hash")
    if _has_type(declared_hash, str) and declared_hash.lower() != computed_hash:
        errors.append(
            "manifest.content_hash: does not match sha256 over the section "
            "files in manifest order + questions.json + the media files in "
            f"manifest order; manifest says {declared_hash}, computed "
            f"{computed_hash}. Package contents changed after export."
        )

    if errors:
        return errors

    # 7.02.5: only `body` sections. The exclusions the paragraph names —
    # introduction, participant instructions, biographies, table of
    # contents, glossary, pre-program assessment, appendixes of
    # supplementary reference material — all carry another role, and their
    # words never reach this sum.
    body_words = sum(
        section.word_count
        for section in sections
        if section.role == COUNTED_ROLE
    )
    return ValidatedPackage(
        lesson_id=manifest["lesson_id"],
        title=manifest["title"],
        content_hash=computed_hash,
        # The lesson's actual audio/video duration time (7.02.7): the sum
        # of its supplemental clips, each measured here by ffprobe.
        duration_seconds=sum(item.duration_seconds for item in media),
        duration_source="measured",
        measured_at=None,
        narration_blocks=0,
        word_count=body_words,
        # Structural for a text package, and enforced item by item above.
        av_is_additional_learning=True,
        field_of_study=field_of_study,
        knowledge_level=knowledge_level,
        prerequisites=prerequisites,
        advance_preparation=advance_preparation,
        manifest=manifest,
        questions=questions,
        kind=KIND_TEXT,
        word_count_source=WORD_COUNT_COMPUTED,
        sections=sections,
        media=media,
        glossary_terms=list(manifest["glossary_terms"]),
        warnings=warnings,
    )


def _validate_sections(
    manifest: dict, package_dir: Path, inner: set[str], errors: list[str]
) -> tuple[list[SectionSpec], list[bytes]]:
    """The guide. Roles decide what 7.02.5 counts, so every one of them is
    checked against the contract's four and at least one `body` section is
    required — a text package with nothing to read is not a program."""
    sections: list[SectionSpec] = []
    section_bytes: list[bytes] = []
    raw = manifest.get("sections")
    if not isinstance(raw, list):
        return sections, section_bytes
    if not raw:
        errors.append("manifest.sections: must not be empty")
        return sections, section_bytes

    seen: set[str] = set()
    for i, entry in enumerate(raw):
        label = f"manifest.sections[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: expected an object with id, file, role, title")
            continue
        if not _check_fields(entry, SECTION_FIELDS, label, errors):
            continue
        key = entry["id"]
        if not key.strip():
            errors.append(f"{label}.id: must be a non-blank string")
            continue
        if key in seen:
            errors.append(f'{label}.id: duplicate section id "{key}"')
            continue
        seen.add(key)
        if not entry["title"].strip():
            errors.append(f"{label}.title: must be a non-blank string")
        if entry["role"] not in SECTION_ROLES:
            errors.append(
                f'{label}.role: "{entry["role"]}" is not one of '
                f"{', '.join(SECTION_ROLES)}; only '{COUNTED_ROLE}' sections "
                "enter the word count (7.02.5)"
            )
        name = entry["file"]
        if not name.startswith(GUIDE_DIR):
            errors.append(
                f'{label}.file: "{name}" must live under {GUIDE_DIR}'
            )
            continue
        if name not in inner:
            errors.append(f'{label}.file: "{name}" is not in the package')
            continue
        data = (package_dir / name).read_bytes()
        try:
            markdown = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{name}: not valid UTF-8")
            continue
        if not markdown.strip():
            errors.append(f"{name}: is blank; a section must have content")
            continue
        section_bytes.append(data)
        sections.append(
            SectionSpec(
                section_key=key,
                role=entry["role"],
                title=entry["title"],
                position=len(sections) + 1,
                file=name,
                markdown=markdown,
                word_count=word_count_service.count_words(markdown),
            )
        )

    if sections and not any(s.role == COUNTED_ROLE for s in sections):
        errors.append(
            f"manifest.sections: at least one '{COUNTED_ROLE}' section is "
            "required; only body sections are counted as required reading "
            "(7.02.5), so a package without one measures zero words"
        )
    return sections, section_bytes


def _validate_media(
    manifest: dict,
    package_dir: Path,
    inner: set[str],
    section_keys: set[str],
    errors: list[str],
) -> tuple[list[MediaSpec], list[bytes]]:
    """Supplemental clips. Every one must claim additional learning and
    every one is measured here, never declared: the manifest's
    `duration_seconds` may be null, and where it is not it must agree with
    ffprobe within a second, exactly as for a video package."""
    media: list[MediaSpec] = []
    media_bytes: list[bytes] = []
    raw = manifest.get("media") or []
    if not isinstance(raw, list):
        return media, media_bytes

    seen: set[str] = set()
    for i, entry in enumerate(raw):
        label = f"manifest.media[{i}]"
        if not isinstance(entry, dict):
            errors.append(
                f"{label}: expected an object with id, file, placement, "
                "av_is_additional_learning"
            )
            continue
        if not _check_fields(entry, MEDIA_FIELDS, label, errors):
            continue
        key = entry["id"]
        if not key.strip():
            errors.append(f"{label}.id: must be a non-blank string")
            continue
        if key in seen:
            errors.append(f'{label}.id: duplicate media id "{key}"')
            continue
        seen.add(key)

        if entry.get("av_is_additional_learning") is not True:
            errors.append(
                f"{label}.av_is_additional_learning: must be true. "
                + ADDITIONAL_LEARNING_SENTENCE
            )

        after_section = entry["placement"].get("after_section")
        if not isinstance(after_section, str) or not after_section.strip():
            errors.append(
                f"{label}.placement.after_section: must name the section "
                "this clip plays after"
            )
            after_section = None
        elif after_section not in section_keys:
            errors.append(
                f'{label}.placement.after_section: "{after_section}" is not '
                "a section id in this manifest"
            )
            after_section = None

        name = entry["file"]
        if not name.startswith(MEDIA_DIR):
            errors.append(f'{label}.file: "{name}" must live under {MEDIA_DIR}')
            continue
        if name not in inner:
            errors.append(f'{label}.file: "{name}" is not in the package')
            continue
        path = package_dir / name
        try:
            measured = ffprobe.duration_seconds(path)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue
        declared = entry.get("duration_seconds")
        if declared is not None:
            if not _has_type(declared, int):
                errors.append(
                    f"{label}.duration_seconds: expected int or null, got "
                    f"{type(declared).__name__}"
                )
            elif abs(Decimal(declared) - measured) > DURATION_TOLERANCE_SECONDS:
                errors.append(
                    f"{label}.duration_seconds: manifest declares {declared} "
                    f"seconds but ffprobe measured {measured} seconds; they "
                    "must agree within 1 second"
                )
        # Truncated, never rounded: a term of the formula may understate,
        # never overstate (7.02.6 rounds down throughout).
        seconds = int(measured)
        if seconds < 1:
            errors.append(
                f"{name}: ffprobe measured {measured} seconds; a supplemental "
                "clip shorter than a second contributes no countable "
                "audio/video duration time (7.02.7)"
            )
            continue
        if after_section is None:
            continue
        media_bytes.append(path.read_bytes())
        media.append(
            MediaSpec(
                media_key=key,
                file=name,
                path=path,
                duration_seconds=seconds,
                after_section=after_section,
                position=len(media) + 1,
                av_is_additional_learning=True,
            )
        )
    return media, media_bytes


def _validate_glossary(
    manifest: dict,
    section_keys: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    """4.05.3 item 3: "the definition of key terms (for example, a glossary
    or a search function that takes a participant to the definition of a
    key word)". An empty list warns here and refuses at the publish gate —
    a package is worth keeping while the course built on it is not yet
    publishable."""
    raw = manifest.get("glossary_terms")
    if not isinstance(raw, list):
        return
    if not raw:
        warnings.append(
            "manifest.glossary_terms: empty. 4.05.3 requires instructional "
            "materials to define key terms, and a course whose text lessons "
            "carry no glossary terms cannot be published."
        )
        return
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        label = f"manifest.glossary_terms[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: expected an object with term and definition")
            continue
        if not _check_fields(entry, GLOSSARY_FIELDS, label, errors):
            continue
        term = entry["term"].strip()
        if not term:
            errors.append(f"{label}.term: must be a non-blank string")
            continue
        if term in seen:
            errors.append(f'{label}.term: duplicate term "{term}"')
        seen.add(term)
        if not entry["definition"].strip():
            errors.append(f"{label}.definition: must be a non-blank string")
        section_id = entry.get("section_id")
        if section_id is not None and section_id not in section_keys:
            errors.append(
                f'{label}.section_id: "{section_id}" is not a section id in '
                "this manifest"
            )


def _is_seconds(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_blocks(video: dict, transcript: str, errors: list[str]) -> None:
    blocks = video["blocks"]
    headings = [
        line[3:].strip()
        for line in transcript.split("\n")
        if line.startswith("## ")
    ]
    if len(blocks) != len(headings):
        errors.append(
            f"manifest.video.blocks: {len(blocks)} entries but transcript.md "
            f"has {len(headings)} block headings; one entry per narrated block"
        )
    narration_blocks = video.get("narration_blocks")
    if _has_type(narration_blocks, int) and len(blocks) != narration_blocks:
        errors.append(
            f"manifest.video.blocks: {len(blocks)} entries does not equal "
            f"narration_blocks ({narration_blocks})"
        )
    prev_end = None
    for i, entry in enumerate(blocks):
        label = f"manifest.video.blocks[{i}]"
        if not isinstance(entry, dict):
            errors.append(
                f"{label}: expected an object with id, start_seconds, end_seconds"
            )
            prev_end = None
            continue
        block_id = entry.get("id")
        if not isinstance(block_id, str) or not block_id.strip():
            errors.append(f"{label}.id: must be a non-blank string")
        elif len(blocks) == len(headings) and block_id != headings[i]:
            errors.append(
                f'{label}.id: "{block_id}" does not match transcript.md heading '
                f'"{headings[i]}" — entries are in playback order'
            )
        start = entry.get("start_seconds")
        end = entry.get("end_seconds")
        if not _is_seconds(start):
            errors.append(
                f"{label}.start_seconds: expected a number, got {type(start).__name__}"
            )
        if not _is_seconds(end):
            errors.append(
                f"{label}.end_seconds: expected a number, got {type(end).__name__}"
            )
        if not _is_seconds(start) or not _is_seconds(end):
            prev_end = None
            continue
        if start < 0:
            errors.append(f"{label}.start_seconds: must be >= 0, got {start}")
        if end <= start:
            errors.append(
                f"{label}: end_seconds ({end}) must be greater than "
                f"start_seconds ({start})"
            )
        if prev_end is not None and start != prev_end:
            errors.append(
                f"{label}.start_seconds: {start} does not equal the previous "
                f"entry's end_seconds ({prev_end}); blocks are contiguous"
            )
        prev_end = end
    if prev_end is not None and _has_type(video.get("duration_seconds"), int):
        drift = abs(Decimal(video["duration_seconds"]) - Decimal(str(prev_end)))
        if drift > DURATION_TOLERANCE_SECONDS:
            errors.append(
                f"manifest.video.blocks: last end_seconds ({prev_end}) is "
                f"{drift:.2f}s from duration_seconds "
                f"({video['duration_seconds']}); they must agree within 1 second"
            )


QUESTION_FIELDS = {
    "id": str,
    "kind": str,
    "stem": str,
    "choices": list,
    "correct": str,
    "feedback": str,
    "objective_ids": list,
}


def _validate_questions(
    questions: list,
    objective_ids: set[str],
    video,
    errors: list[str],
    section_keys: set[str] | None = None,
) -> None:
    """Rules 13-17. `section_keys` is given for a text package and switches
    rule 15's placement from `after_block` to `after_section`: the same
    5.01.2.1 requirement — review questions "placed throughout the program
    in sufficient intervals" — expressed in the two media."""
    # Rule 13.
    if not questions:
        errors.append("questions: must not be empty")
    seen_ids: set[str] = set()
    # Rule 15's placement bound: after_block indexes into video.blocks
    # (video-tool 03), so the bound is the list's length.
    blocks = video.get("blocks") if isinstance(video, dict) else None
    block_count = len(blocks) if isinstance(blocks, list) else None
    for i, q in enumerate(questions):
        qid = q.get("id") if isinstance(q, dict) else None
        label = f"questions[{qid}]" if isinstance(qid, str) and qid.strip() else f"questions[{i}]"
        if not isinstance(q, dict):
            errors.append(f"{label}: expected an object")
            continue
        fields_ok = _check_fields(q, QUESTION_FIELDS, label, errors)
        if isinstance(qid, str):
            if qid in seen_ids:
                errors.append(f'{label}.id: duplicate question id "{qid}"')
            seen_ids.add(qid)
        if not fields_ok:
            continue

        kind = q["kind"]
        if kind not in ("review", "assessment"):
            errors.append(f'{label}.kind: must be "review" or "assessment", got "{kind}"')
            continue

        # Rule 14.
        choice_ids = [c.get("id") for c in q["choices"] if isinstance(c, dict)]
        if q["correct"] not in choice_ids:
            errors.append(
                f'{label}.correct: "{q["correct"]}" is not the id of any choice'
            )

        # Rule 15.
        if kind == "review":
            if len(q["choices"]) < REVIEW_MIN_CHOICES:
                errors.append(
                    f"{label}.choices: review questions need at least "
                    f"{REVIEW_MIN_CHOICES} choices, got {len(q['choices'])}"
                )
            if section_keys is None:
                after_block = q.get("after_block")
                if not _has_type(after_block, int):
                    errors.append(
                        f"{label}.after_block: review questions require an integer after_block"
                    )
                elif block_count is not None and not (1 <= after_block <= block_count):
                    errors.append(
                        f"{label}.after_block: {after_block} is outside "
                        f"[1, {block_count}] (video.blocks)"
                    )
            else:
                after_section = q.get("after_section")
                if not isinstance(after_section, str) or not after_section.strip():
                    errors.append(
                        f"{label}.after_section: review questions in a text "
                        "package require the id of the section they follow"
                    )
                elif after_section not in section_keys:
                    errors.append(
                        f'{label}.after_section: "{after_section}" is not a '
                        "section id in this manifest"
                    )
                if "after_block" in q:
                    errors.append(
                        f"{label}.after_block: a text package places review "
                        "questions by after_section, not after_block"
                    )
        else:
            if len(q["choices"]) < ASSESSMENT_MIN_CHOICES:
                errors.append(
                    f"{label}.choices: assessment questions need at least "
                    f"{ASSESSMENT_MIN_CHOICES} choices (6.01.2 forced-choice "
                    f"prohibition), got {len(q['choices'])}"
                )
            if "after_block" in q:
                errors.append(
                    f"{label}.after_block: assessment questions must not have after_block"
                )
            if "after_section" in q:
                errors.append(
                    f"{label}.after_section: assessment questions must not "
                    "have after_section"
                )

        # Rule 16.
        if not q["objective_ids"]:
            errors.append(
                f"{label}.objective_ids: every question must map to at least one "
                "learning objective"
            )
        for oid in q["objective_ids"]:
            if oid not in objective_ids:
                errors.append(
                    f'{label}.objective_ids: "{oid}" is not a learning objective '
                    "id in the manifest"
                )

        # Rule 17.
        if not q["feedback"].strip():
            errors.append(f"{label}.feedback: must not be blank")


def ingest(
    db: Session, storage: Storage, validated: ValidatedPackage
) -> tuple[LessonPackage, bool]:
    existing = db.scalar(
        select(LessonPackage).where(
            LessonPackage.content_hash == validated.content_hash
        )
    )
    if existing is not None:
        return existing, False

    latest = db.scalar(
        select(func.max(LessonPackage.version)).where(
            LessonPackage.lesson_id == validated.lesson_id
        )
    )
    version = (latest or 0) + 1
    prefix = f"packages/{validated.lesson_id}/v{version}"
    is_text = validated.kind == KIND_TEXT
    video_key = None if is_text else f"{prefix}/video.mp4"

    package = LessonPackage(
        kind=validated.kind,
        lesson_id=validated.lesson_id,
        version=version,
        content_hash=validated.content_hash,
        title=validated.title,
        duration_seconds=validated.duration_seconds,
        duration_source=validated.duration_source,
        measured_at=validated.measured_at,
        narration_blocks=validated.narration_blocks,
        word_count=validated.word_count,
        word_count_source=validated.word_count_source,
        av_is_additional_learning=validated.av_is_additional_learning,
        field_of_study=validated.field_of_study,
        knowledge_level=validated.knowledge_level,
        prerequisites=validated.prerequisites,
        advance_preparation=validated.advance_preparation,
        manifest=validated.manifest,
        questions=validated.questions,
        transcript=validated.transcript,
        video_key=video_key,
    )
    # The guide, its clips, and its key terms are written in the same
    # transaction as the package row, for the same reason the questions
    # are: a package version never exists without the material it is.
    package.sections = [
        PackageSection(
            section_key=section.section_key,
            role=section.role,
            title=section.title,
            position=section.position,
            file=section.file,
            markdown=section.markdown,
            word_count=section.word_count,
        )
        for section in validated.sections
    ]
    package.media = [
        PackageMedia(
            media_key=item.media_key,
            file=item.file,
            storage_key=f"{prefix}/{item.file}",
            duration_seconds=item.duration_seconds,
            after_section=item.after_section,
            position=item.position,
            av_is_additional_learning=item.av_is_additional_learning,
        )
        for item in validated.media
    ]
    package.glossary_terms = [
        GlossaryTerm(
            term=entry["term"].strip(),
            definition=entry["definition"].strip(),
            section_key=entry.get("section_id"),
            position=position,
        )
        for position, entry in enumerate(validated.glossary_terms, start=1)
    ]
    try:
        db.add(package)
        db.flush()
        # Same transaction as the package row: a package never exists
        # without its normalized question rows.
        questions_service.normalize(db, package)
        if is_text:
            for item, row in zip(validated.media, package.media):
                with open(item.path, "rb") as fileobj:
                    storage.put(row.storage_key, fileobj)
        else:
            with open(validated.video_path, "rb") as fileobj:
                storage.put(video_key, fileobj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(package)
    return package, True


def overview(package: LessonPackage) -> dict:
    """The human summary of a stored package, for the admin package view.

    Derived on read, never stored: the counts are sums over the rows the
    package already has. What it exists to make visible without reading
    raw JSON is the 7.02.5 split — which sections' words counted, which
    did not, and whether the total was computed here or trusted from the
    manifest."""
    by_role: dict[str, dict] = {}
    for section in package.sections:
        entry = by_role.setdefault(
            section.role,
            {
                "role": section.role,
                "label": ROLE_LABELS[section.role],
                "sections": 0,
                "words": 0,
                "counted": section.role == COUNTED_ROLE,
            },
        )
        entry["sections"] += 1
        entry["words"] += section.word_count
    questions = package.questions or []
    return {
        "kind": package.kind,
        "word_count_source": package.word_count_source,
        "word_count": package.word_count,
        # Every word shipped, counted or not: the difference between this
        # and `word_count` is exactly what 7.02.5 excludes.
        "total_words": sum(s.word_count for s in package.sections),
        "sections_by_role": [
            by_role[role] for role in SECTION_ROLES if role in by_role
        ],
        "media_count": len(package.media),
        "media_seconds": sum(m.duration_seconds for m in package.media),
        "review_questions": sum(
            1 for q in questions if q.get("kind") == "review"
        ),
        "assessment_questions": sum(
            1 for q in questions if q.get("kind") == "assessment"
        ),
    }


def list_packages(db: Session) -> list[LessonPackage]:
    packages = list(
        db.scalars(
            select(LessonPackage).order_by(
                LessonPackage.ingested_at.desc(), LessonPackage.id.desc()
            )
        )
    )
    attachments = {
        lesson.package_id: lesson.course.course_code
        for lesson in db.scalars(select(CourseLesson))
    }
    for package in packages:
        package.attached_to = attachments.get(package.id)
    return packages


def get_package(db: Session, package_id: int) -> LessonPackage | None:
    return db.get(LessonPackage, package_id)


def delete_package(db: Session, storage: Storage, package_id: int) -> bool:
    """Deletes an unattached package and its storage object. Returns False
    if the package does not exist; refuses if it is attached to a course."""
    package = db.get(LessonPackage, package_id)
    if package is None:
        return False
    attachment = db.scalar(
        select(CourseLesson).where(CourseLesson.package_id == package_id)
    )
    if attachment is not None:
        raise CourseRuleViolation(
            [
                f"package {package.lesson_id} v{package.version} is attached "
                f"to course {attachment.course.course_code}; detach it before "
                "deleting"
            ]
        )
    # Collected before the delete cascades the media rows away.
    keys = [row.storage_key for row in package.media]
    if package.video_key is not None:
        keys.append(package.video_key)
    db.delete(package)
    db.commit()
    for key in keys:
        storage.delete(key)
    return True
