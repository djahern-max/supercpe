"""Validate and ingest lesson packages per docs/course-package.md.

`validate` runs every contract rule against a package zip and either returns
a ValidatedPackage or the full list of failure messages. It touches no
database and no storage. `ingest` handles idempotency and versioning and is
the only writer.
"""

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.fields_of_study import FIELDS_OF_STUDY
from app.constants.knowledge_levels import (
    KNOWLEDGE_LEVELS,
    LEVELS_REQUIRING_PREREQUISITES,
    PREREQUISITES_NONE,
)
from app.models.course import CourseLesson
from app.models.lesson_package import LessonPackage
from app.services import ffprobe
from app.services import questions as questions_service
from app.services.courses import CourseRuleViolation
from app.storage import Storage

PACKAGE_FILES = ("manifest.json", "video.mp4", "transcript.md", "questions.json")

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
ASSESSMENT_MIN_CHOICES = 3


@dataclass
class ValidatedPackage:
    lesson_id: str
    title: str
    content_hash: str
    duration_seconds: int
    duration_source: str
    measured_at: datetime
    narration_blocks: int
    word_count: int
    av_is_additional_learning: bool
    field_of_study: str
    knowledge_level: str
    prerequisites: str
    advance_preparation: str
    manifest: dict
    questions: list
    transcript: str
    video_path: Path


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

    # Rule 2: package_version.
    version = manifest.get("package_version")
    if _has_type(version, int) and version != 1:
        errors.append(f"manifest.package_version: expected 1, received {version}")

    if _has_type(manifest.get("course_code"), str) and not manifest["course_code"].strip():
        errors.append("manifest.course_code: must be a non-blank string")
    if _has_type(manifest.get("position"), int) and manifest["position"] < 1:
        errors.append(
            f"manifest.position: must be a positive integer, got {manifest['position']}"
        )

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
    questions: list, objective_ids: set[str], video, errors: list[str]
) -> None:
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
    video_key = f"packages/{validated.lesson_id}/v{version}/video.mp4"

    package = LessonPackage(
        lesson_id=validated.lesson_id,
        version=version,
        content_hash=validated.content_hash,
        title=validated.title,
        duration_seconds=validated.duration_seconds,
        duration_source=validated.duration_source,
        measured_at=validated.measured_at,
        narration_blocks=validated.narration_blocks,
        word_count=validated.word_count,
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
    try:
        db.add(package)
        db.flush()
        # Same transaction as the package row: a package never exists
        # without its normalized question rows.
        questions_service.normalize(db, package)
        with open(validated.video_path, "rb") as fileobj:
            storage.put(video_key, fileobj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(package)
    return package, True


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
    video_key = package.video_key
    db.delete(package)
    db.commit()
    storage.delete(video_key)
    return True
