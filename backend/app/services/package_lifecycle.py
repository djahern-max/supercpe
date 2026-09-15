"""038: a package version's lifecycle — delete, archive, purge media.

Lessons are re-exported as they improve, and every re-upload is a new
version. A superseded version is in one of three positions, all derived
here from the records that reference it, never stored as flags:

- **unused** — no enrollment and no preview sitting references it, and no
  course has it attached: it can be deleted outright, rows and files.
- **used, within retention** — it can be *archived*: hidden from the
  packages list and refused as an attachment, every row and file kept.
- **used, past retention** — once archived, its stored video and media
  files can be *purged*. The database rows (manifest, transcript, sections,
  questions, choices) and every participant record stay; only the program
  materials' files go (9.02.2(7)).

"References" are every record that points at a version, FK or not: an
enrollment's `package_versions` pin, `lesson_progress`, `review_answers`
and `attempt_answers` through the version's questions, and an attempt's
`package_versions` list — including preview attempts (007), which are
retained sittings too and whose answers hold the questions just as firmly.

The retention anchor of an enrollment is its completion's `completed_at`
when it completed, else its `expires_at` (the latest moment anything could
have been recorded on it); a preview attempt's is `submitted_at`, else
`started_at`. A version's `retain_until` is the latest `retain_until()` of
those anchors — 9.02's five years run from the last record, not the
upload.

Reverses, for package media files only, 011's "nothing deletes at the
boundary" (`app/constants/retention.py`); see
docs/decisions/2026-09-15-package-version-lifecycle.md.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.attempt import Attempt, AttemptAnswer
from app.models.course import CourseLesson
from app.models.enrollment import Enrollment, LessonProgress, ReviewAnswer
from app.models.lesson_package import LessonPackage
from app.models.question import Question
from app.services.courses import CourseRuleViolation
from app.services.retention import retain_until
from app.storage import Storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(value: datetime) -> str:
    return value.date().isoformat()


@dataclass
class Usage:
    enrollment_ids: set[int] = field(default_factory=set)
    preview_attempt_ids: set[int] = field(default_factory=set)
    anchors: list[datetime] = field(default_factory=list)
    attached_to: list[str] = field(default_factory=list)

    @property
    def used(self) -> bool:
        return bool(self.enrollment_ids or self.preview_attempt_ids)

    @property
    def retain_until(self) -> datetime | None:
        if not self.anchors:
            return None
        return max(retain_until(anchor) for anchor in self.anchors)


def usage_by_package(db: Session, package_ids: list[int]) -> dict[int, Usage]:
    """Every reference to each of `package_ids`, in a fixed handful of
    queries whatever the number of packages."""
    wanted = set(package_ids)
    usage = {package_id: Usage() for package_id in wanted}
    if not wanted:
        return usage

    enrollment_anchor: dict[int, datetime] = {}

    def add_enrollment(package_id: int, enrollment_id: int | None) -> None:
        if package_id not in wanted or enrollment_id is None:
            return
        entry = usage[package_id]
        if enrollment_id not in entry.enrollment_ids:
            entry.enrollment_ids.add(enrollment_id)
            entry.anchors.append(enrollment_anchor[enrollment_id])

    def add_preview(package_id: int, attempt: Attempt) -> None:
        if package_id not in wanted:
            return
        entry = usage[package_id]
        if attempt.id not in entry.preview_attempt_ids:
            entry.preview_attempt_ids.add(attempt.id)
            entry.anchors.append(attempt.submitted_at or attempt.started_at)

    enrollment_rows = list(
        db.scalars(select(Enrollment).options(selectinload(Enrollment.completion)))
    )
    for enrollment in enrollment_rows:
        enrollment_anchor[enrollment.id] = (
            enrollment.completion.completed_at
            if enrollment.completion is not None
            else enrollment.expires_at
        )
    for enrollment in enrollment_rows:
        for key in enrollment.package_versions:
            add_enrollment(int(key), enrollment.id)

    for package_id, enrollment_id in db.execute(
        select(LessonProgress.package_id, LessonProgress.enrollment_id).where(
            LessonProgress.package_id.in_(wanted)
        )
    ):
        add_enrollment(package_id, enrollment_id)

    for package_id, enrollment_id in db.execute(
        select(Question.package_id, ReviewAnswer.enrollment_id)
        .join(Question, ReviewAnswer.question_id == Question.id)
        .where(Question.package_id.in_(wanted))
    ):
        add_enrollment(package_id, enrollment_id)

    attempts = {attempt.id: attempt for attempt in db.scalars(select(Attempt))}

    def add_attempt(package_id: int, attempt: Attempt) -> None:
        if attempt.is_preview:
            add_preview(package_id, attempt)
        else:
            add_enrollment(package_id, attempt.enrollment_id)

    for attempt in attempts.values():
        for entry in attempt.package_versions:
            add_attempt(int(entry["package_id"]), attempt)
    for package_id, attempt_id in db.execute(
        select(Question.package_id, AttemptAnswer.attempt_id)
        .join(Question, AttemptAnswer.question_id == Question.id)
        .where(Question.package_id.in_(wanted))
    ):
        add_attempt(package_id, attempts[attempt_id])

    for lesson in db.scalars(
        select(CourseLesson).where(CourseLesson.package_id.in_(wanted))
    ):
        usage[lesson.package_id].attached_to.append(lesson.course.course_code)
    return usage


def usage_of(db: Session, package: LessonPackage) -> Usage:
    return usage_by_package(db, [package.id])[package.id]


def _name(package: LessonPackage) -> str:
    return f"package {package.lesson_id} v{package.version}"


def _references(usage: Usage) -> str:
    parts = []
    if usage.enrollment_ids:
        count = len(usage.enrollment_ids)
        parts.append(f"{count} enrollment{'' if count == 1 else 's'}")
    if usage.preview_attempt_ids:
        count = len(usage.preview_attempt_ids)
        parts.append(
            f"{count} preview assessment attempt{'' if count == 1 else 's'}"
        )
    return " and ".join(parts)


def _attached_refusal(package: LessonPackage, usage: Usage, act: str) -> list[str]:
    return [
        f"{_name(package)} is attached to course {code}; detach it before {act}"
        for code in usage.attached_to
    ]


def delete_refusals(package: LessonPackage, usage: Usage) -> list[str]:
    errors = _attached_refusal(package, usage, "deleting")
    if usage.used:
        errors.append(
            f"{_name(package)} is referenced by {_references(usage)}; "
            "archive it instead"
        )
    return errors


def deletable(usage: Usage) -> bool:
    return not usage.used and not usage.attached_to


def purge_refusals(
    package: LessonPackage, usage: Usage, now: datetime | None = None
) -> list[str]:
    now = now or _now()
    if package.media_purged_at is not None:
        return [
            f"the media of {_name(package)} were already purged on "
            f"{_day(package.media_purged_at)}"
        ]
    if not usage.used:
        return [
            f"{_name(package)} is not referenced by any participant record; "
            "delete it instead"
        ]
    errors = _attached_refusal(package, usage, "purging its media")
    if package.archived_at is None:
        errors.append(f"archive {_name(package)} before purging its media")
    until = usage.retain_until
    if until is not None and now <= until:
        errors.append(
            f"the records of {_name(package)} must be retained until "
            f"{_day(until)}; its media can be purged after then"
        )
    return errors


def media_purgeable(
    package: LessonPackage, usage: Usage, now: datetime | None = None
) -> bool:
    return not purge_refusals(package, usage, now)


def archive(db: Session, package: LessonPackage) -> LessonPackage:
    usage = usage_of(db, package)
    errors = _attached_refusal(package, usage, "archiving")
    if package.archived_at is not None:
        errors.append(f"{_name(package)} is already archived")
    if errors:
        raise CourseRuleViolation(errors)
    package.archived_at = _now()
    db.commit()
    return package


def unarchive(db: Session, package: LessonPackage) -> LessonPackage:
    if package.archived_at is None:
        raise CourseRuleViolation([f"{_name(package)} is not archived"])
    if package.media_purged_at is not None:
        raise CourseRuleViolation(
            [
                f"the media of {_name(package)} were purged on "
                f"{_day(package.media_purged_at)}; it stays archived"
            ]
        )
    package.archived_at = None
    db.commit()
    return package


def owned_keys(package: LessonPackage) -> list[str]:
    """Every storage object the version owns: its video (video kind) and
    its supplemental media (text kind). Everything else a package ships is
    a database row."""
    keys = [row.storage_key for row in package.media]
    if package.video_key is not None:
        keys.append(package.video_key)
    return keys


def purge_media(
    db: Session, storage: Storage, package: LessonPackage, admin: Account
) -> LessonPackage:
    """Deletes the version's stored files, then records the purge. Files
    first: a storage failure part-way leaves nothing recorded and the purge
    can simply be run again (a delete of an already-missing key succeeds),
    whereas recording first could claim a purge whose files still exist."""
    usage = usage_of(db, package)
    now = _now()
    errors = purge_refusals(package, usage, now)
    if errors:
        raise CourseRuleViolation(errors)
    for key in owned_keys(package):
        storage.delete(key)
    package.media_purged_at = now
    package.media_purged_by = admin.email
    db.commit()
    return package


def media_removed_message(package: LessonPackage) -> str | None:
    """The one sentence every surface shows in place of a purged file."""
    if package.media_purged_at is None:
        return None
    return (
        f"Materials for this version were removed on "
        f"{_day(package.media_purged_at)} after the retention period."
    )
