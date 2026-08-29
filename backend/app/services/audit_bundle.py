"""The per-course audit bundle: the 9.02.2 self study documentation set as
one zip a NASBA reviewer could read cold (ROADMAP structural difference 5).

`build` assembles the zip in memory from the rows and storage; nothing it
reads is mutated. `create_export` stores the zip and logs an
`audit_exports` row — every export is kept, because an export is itself
documentation of what the sponsor could produce on a date. Videos are
included by reference (storage key in video.txt) unless `include_video`;
CSVs are UTF-8 with a header row; timestamps are ISO 8601 UTC.
"""

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.enrollment import ENROLLMENT_DAYS
from app.constants.evaluation import PROMPTS, RATED_ELEMENTS
from app.constants.retention import RETENTION_YEARS
from app.models.account import Account
from app.models.attempt import Attempt
from app.models.audit import AuditExport
from app.models.course import Course
from app.models.enrollment import Enrollment, ReviewAnswer
from app.models.lesson_package import LessonPackage
from app.services import credit, development
from app.services import enrollments as enrollments_service
from app.services import evaluations as evaluations_service
from app.services import policies as policies_service
from app.services import sponsor as sponsor_service
from app.services.instructions import how_it_works_markdown
from app.services.retention import retain_until
from app.storage import Storage

# 9.02.2's seven elements, quoted, mapped to the bundle's directories.
# README.md renders this table; the order is the paragraph's own.
ELEMENT_MAP = [
    (
        "1-completion/",
        "9.02.2(1)",
        "Records of program completion verification by individual "
        "participant, including the number of CPE credits earned by "
        "participant and course completion date.",
    ),
    (
        "2-credit/",
        "9.02.2(2)",
        "Documentation of how CPE credits were determined.",
    ),
    (
        "3-expiration/",
        "9.02.2(3)",
        "Course documentation must include an expiration date (the time by "
        "which the participant must complete the qualified assessment). For "
        "individual courses, the expiration date is no longer than one year "
        "from the date of purchase or enrollment.",
    ),
    (
        "4-people/",
        "9.02.2(4)",
        "Author/instructor, author/developer, and content reviewer, as "
        "applicable, names and credentials.",
    ),
    ("5-evaluations/", "9.02.2(5)", "Results of program evaluations."),
    (
        "6-descriptive/",
        "9.02.2(6)",
        "Program descriptive materials (course announcement information).",
    ),
    ("7-materials/", "9.02.2(7)", "Program materials."),
]


def _ts(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""


def _csv_bytes(header: list[str], rows: list[list], comments: list[str] = ()) -> bytes:
    out = io.StringIO()
    for line in comments:
        out.write(f"# {line}\n")
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _json_bytes(payload) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def build(
    db: Session,
    storage: Storage,
    course: Course,
    generated_by: Account,
    include_video: bool = False,
) -> tuple[bytes, dict]:
    """Assemble the bundle. Returns (zip bytes, the bundle.json manifest).

    Every file is listed in bundle.json with its sha256 and byte size
    (bundle.json cannot list itself); the zip holds one top-level directory
    `<course_code>-audit-<YYYYMMDD>/`."""
    generated_at = datetime.now(timezone.utc)
    files: dict[str, bytes] = {}

    enrollments = sorted(
        enrollments_service.list_for_course(db, course), key=lambda e: e.id
    )
    attempts = list(
        db.scalars(
            select(Attempt)
            .where(Attempt.course_id == course.id)
            .order_by(Attempt.started_at, Attempt.id)
        )
    )

    _completion_files(db, storage, course, enrollments, attempts, files)
    _credit_files(course, files)
    _expiration_files(enrollments, files)
    _people_files(course, files)
    _evaluation_files(db, course, files)
    _descriptive_files(db, course, files)
    _material_files(db, storage, course, enrollments, attempts, include_video, files)
    files["README.md"] = _readme(db, course, generated_by, generated_at).encode(
        "utf-8"
    )

    manifest = {
        "generated_at": _ts(generated_at),
        "generated_by": generated_by.email,
        "course_code": course.course_code,
        "files": [
            {
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for path, content in sorted(files.items())
        ],
    }
    files["bundle.json"] = _json_bytes(manifest)

    top = f"{course.course_code}-audit-{generated_at:%Y%m%d}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(f"{top}/{path}", content)
    return buffer.getvalue(), manifest


def _completion_files(
    db: Session,
    storage: Storage,
    course: Course,
    enrollments: list[Enrollment],
    attempts: list[Attempt],
    files: dict,
) -> None:
    completions = [e.completion for e in enrollments if e.completion is not None]
    files["1-completion/completions.csv"] = _csv_bytes(
        [
            "name",
            "email",
            "enrolled_at",
            "expires_at",
            "completed_at",
            "credit_awarded",
            "certificate_number",
            "retain_until",
        ],
        [
            [
                c.enrollment.account.display_name,
                c.enrollment.account.email,
                _ts(c.enrollment.enrolled_at),
                _ts(c.enrollment.expires_at),
                _ts(c.completed_at),
                str(c.credit_awarded),
                c.certificate_number,
                _ts(retain_until(c.completed_at)),
            ]
            for c in completions
        ],
    )
    files["1-completion/attempts.csv"] = _csv_bytes(
        [
            "attempt_id",
            "participant",
            "started_at",
            "submitted_at",
            "status",
            "score_pct",
            "passing_pct",
            "package_versions",
        ],
        [
            [
                a.id,
                a.enrollment.account.email if a.enrollment else "(preview)",
                _ts(a.started_at),
                _ts(a.submitted_at),
                a.status,
                str(a.score_pct) if a.score_pct is not None else "",
                str(a.passing_pct),
                json.dumps(a.package_versions),
            ]
            for a in attempts
        ],
    )
    files["1-completion/attempt_answers.csv"] = _csv_bytes(
        ["attempt_id", "question_key", "chosen", "correct"],
        [
            [
                a.id,
                answer.question.question_key,
                answer.choice.choice_key,
                "" if answer.is_correct is None else str(answer.is_correct).lower(),
            ]
            for a in attempts
            for answer in sorted(a.answers, key=lambda x: x.id)
        ],
    )
    review_answers = list(
        db.scalars(
            select(ReviewAnswer)
            .join(Enrollment, ReviewAnswer.enrollment_id == Enrollment.id)
            .where(Enrollment.course_id == course.id)
            .order_by(ReviewAnswer.answered_at, ReviewAnswer.id)
        )
    )
    files["1-completion/review_answers.csv"] = _csv_bytes(
        [
            "enrollment_id",
            "lesson_id",
            "question_key",
            "chosen",
            "correct",
            "answered_at",
        ],
        [
            [
                row.enrollment_id,
                db.get(LessonPackage, row.question.package_id).lesson_id,
                row.question.question_key,
                next(
                    c.choice_key
                    for c in row.question.choices
                    if c.id == row.choice_id
                ),
                str(row.is_correct).lower(),
                _ts(row.answered_at),
            ]
            for row in review_answers
        ],
    )
    for completion in completions:
        files[
            f"1-completion/certificates/{completion.certificate_number}.json"
        ] = _json_bytes(completion.certificate_snapshot)
        if completion.certificate_key and storage.exists(
            completion.certificate_key
        ):
            with storage.open(completion.certificate_key) as pdf:
                files[
                    f"1-completion/certificates/"
                    f"{completion.certificate_number}.pdf"
                ] = pdf.read()


def _credit_files(course: Course, files: dict) -> None:
    breakdown = credit.from_stored(course)
    files["2-credit/calculation.txt"] = (
        credit.as_text(breakdown) if breakdown else "No credit measurement is stored."
    ).encode("utf-8")
    files["2-credit/credit_breakdown.json"] = _json_bytes(
        course.credit_breakdown or []
    )


def _expiration_files(enrollments: list[Enrollment], files: dict) -> None:
    files["3-expiration/enrollments.csv"] = _csv_bytes(
        [
            "enrollment_id",
            "participant",
            "enrolled_at",
            "expires_at",
            "status",
            "package_versions",
        ],
        [
            [
                e.id,
                e.account.email,
                _ts(e.enrolled_at),
                _ts(e.expires_at),
                enrollments_service.status(e),
                json.dumps(e.package_versions),
            ]
            for e in enrollments
        ],
    )
    files["3-expiration/policy.txt"] = (
        f"ENROLLMENT_DAYS = {ENROLLMENT_DAYS}\n"
        "Every enrollment expires this many days after enrollment; the\n"
        "qualified assessment must be completed by then.\n\n"
        '9.02.2(3): "Course documentation must include an expiration date\n'
        "(the time by which the participant must complete the qualified\n"
        "assessment). For individual courses, the expiration date is no\n"
        "longer than one year from the date of purchase or enrollment.\"\n"
    ).encode("utf-8")


def _sme_record(sme) -> dict | None:
    """The 9.02.2(4) record: names, credentials, and the license facts
    that must be maintained. The bundle is the one place license numbers
    may appear; they never reach a public payload."""
    if sme is None:
        return None
    return {
        "name": sme.name,
        "credentials": sme.credentials,
        "credential_type": sme.credential_type,
        "license_jurisdiction": sme.license_jurisdiction,
        "license_number": sme.license_number,
        "license_status": sme.license_status,
    }


def _people_files(course: Course, files: dict) -> None:
    developer = _sme_record(course.developer)
    if developer is not None:
        developer["developer_used_technology"] = course.developer_used_technology
    files["4-people/developer.json"] = _json_bytes(developer)

    seen = {}
    for review in sorted(course.reviews, key=lambda r: r.id):
        seen.setdefault(review.reviewer_id, review.reviewer)
    files["4-people/reviewers.json"] = _json_bytes(
        [_sme_record(sme) for sme in seen.values()]
    )
    files["4-people/reviews.csv"] = _csv_bytes(
        [
            "reviewed_at",
            "reviewer",
            "decision",
            "notes",
            "impractical_basis",
            "content_updated_at_reviewed",
            "recorded_by",
            "created_at",
        ],
        [
            [
                review.reviewed_at.isoformat(),
                review.reviewer.name,
                review.decision,
                review.notes,
                review.impractical_basis or "",
                _ts(review.content_updated_at_reviewed),
                review.recorded_by,
                _ts(review.created_at),
            ]
            for review in sorted(course.reviews, key=lambda r: r.id)
        ],
    )
    current = development.current_review(course)
    due = development.review_due_at(course)
    files["4-people/review_cycle.txt"] = (
        f"review_cycle: {course.review_cycle}\n"
        f"current review: "
        f"{current.reviewed_at.isoformat() if current else 'none'}\n"
        f"review_due_at: {due.isoformat() if due else 'n/a'}\n"
    ).encode("utf-8")


def _evaluation_files(db: Session, course: Course, files: dict) -> None:
    prompts = [f'{element}: "{PROMPTS[element]}"' for element in RATED_ELEMENTS]
    prompts.append(f'instructors_effective: "{PROMPTS["instructors_effective"]}"')
    files["5-evaluations/evaluations.csv"] = _csv_bytes(
        [
            "submitted_at",
            *RATED_ELEMENTS,
            "instructors_effective",
            "comments",
        ],
        [
            [
                _ts(row.submitted_at),
                *[getattr(row, element) for element in RATED_ELEMENTS],
                "not applicable (self study)",
                row.comments,
            ]
            for row in evaluations_service.for_course(db, course)
        ],
        comments=["Prompts as asked (app/constants/evaluation.py):"] + prompts,
    )
    files["5-evaluations/summary.json"] = _json_bytes(
        evaluations_service.summary(db, course)
    )
    files["5-evaluations/evaluation_reviews.csv"] = _csv_bytes(
        ["reviewed_at", "reviewed_by", "informed_developer", "note", "n"],
        [
            [
                _ts(review.reviewed_at),
                review.reviewed_by.email,
                str(review.informed_developer).lower(),
                review.note,
                review.summary_snapshot.get("n", ""),
            ]
            for review in reversed(
                evaluations_service.reviews_for_course(db, course)
            )
        ],
    )


def _descriptive_files(db: Session, course: Course, files: dict) -> None:
    # Deferred import: the router imports services, and this is the one
    # payload that must be byte-identical with what the public route serves.
    from app.routers.courses import public_detail

    payload = public_detail(course)
    files["6-descriptive/course.json"] = _json_bytes(
        payload.model_dump(mode="json")
    )
    files["6-descriptive/course.md"] = _course_markdown(payload).encode("utf-8")

    for kind in policies_service.KIND_LABELS:
        for n, version in enumerate(
            reversed(policies_service.versions_of(db, kind)), start=1
        ):
            files[f"6-descriptive/policies/{kind}-{n}.md"] = (
                f"# {policies_service.KIND_LABELS[kind]} policy "
                f"(version {n})\n\n"
                f"Effective: {_ts(version.effective_at)}\n\n"
                f"{version.body}\n"
            ).encode("utf-8")
    files["6-descriptive/how-it-works.md"] = how_it_works_markdown().encode(
        "utf-8"
    )


def _course_markdown(payload) -> str:
    lines = [
        f"# {payload.title}",
        "",
        payload.description,
        "",
        f"- Course code: {payload.course_code}",
        f"- Field of study: {payload.field_of_study}",
        f"- Knowledge level: {payload.knowledge_level}",
        f"- Prerequisites: {payload.prerequisites}",
        f"- Advance preparation: {payload.advance_preparation}",
        f"- Recommended CPE credit: {payload.recommended_credit} "
        f"({payload.credit_basis})",
        "",
        "## What this course covers",
        "",
    ]
    for lesson in payload.outline:
        lines.append(f"### {lesson.position}. {lesson.title}")
        lines += [f"- {objective.text}" for objective in lesson.objectives]
        lines.append("")
    if payload.developed_by:
        lines.append(f"Developed by {payload.developed_by.name}.")
    if payload.reviewed_by:
        lines.append(f"Reviewed by {payload.reviewed_by.name}.")
    return "\n".join(lines) + "\n"


def _material_files(
    db: Session,
    storage: Storage,
    course: Course,
    enrollments: list[Enrollment],
    attempts: list[Attempt],
    include_video: bool,
    files: dict,
) -> None:
    """Every package version ever attached or pinned: the current lessons,
    every enrollment's pinned versions, and every attempt's recorded
    versions."""
    package_ids = {cl.package_id for cl in course.lessons}
    for enrollment in enrollments:
        package_ids |= {int(pid) for pid in enrollment.package_versions}
    for attempt in attempts:
        package_ids |= {entry["package_id"] for entry in attempt.package_versions}

    for package_id in sorted(package_ids):
        package = db.get(LessonPackage, package_id)
        prefix = f"7-materials/{package.lesson_id}/v{package.version}"
        files[f"{prefix}/manifest.json"] = _json_bytes(package.manifest)
        files[f"{prefix}/questions.json"] = _json_bytes(package.questions)
        files[f"{prefix}/transcript.md"] = package.transcript.encode("utf-8")
        files[f"{prefix}/video.txt"] = (
            f"storage_key: {package.video_key}\n"
            f"content_hash: {package.content_hash}\n"
            f"duration_seconds: {package.duration_seconds}\n"
            "video omitted; retrieve by key\n"
        ).encode("utf-8")
        if include_video and storage.exists(package.video_key):
            with storage.open(package.video_key) as video:
                files[f"{prefix}/video.mp4"] = video.read()


def _readme(
    db: Session, course: Course, generated_by: Account, generated_at: datetime
) -> str:
    profile = sponsor_service.get_profile(db)
    if profile.may_claim_registry:
        # The registry status as of generation, stated plainly to an
        # auditor.
        registry_line = (
            "This sponsor is registered on the National Registry of CPE "
            f"Sponsors (sponsor ID {profile.national_registry_id})."
        )
    else:
        # The one place this sentence is allowed: it is the truth stated
        # to an auditor, never a claim.
        registry_line = (
            "This sponsor is not on the National Registry of CPE Sponsors."
        )

    element_lines = "\n".join(
        f"- `{directory}` — {locator}: \"{text}\""
        for directory, locator, text in ELEMENT_MAP
    )
    return f"""# Audit bundle: {course.course_code} — {course.title}

Sponsor: {profile.name} ({profile.legal_name})

Documentation retained under Section 9 of the 2026 Statement on Standards
for CPE Programs for self study programs. {registry_line}

Generated by {generated_by.email} at {_ts(generated_at)}.

## Retention

9.02 requires this documentation retained for a minimum of
{RETENTION_YEARS} years. Each completion record in
`1-completion/completions.csv` states its own `retain_until` date;
nothing is deleted at that boundary — the period is a floor.

## The 9.02.2 documentation elements

Each required element of self study program documentation maps to one
directory of this bundle:

{element_lines}

Notes:

- CPE credit rests on method 2, the prescribed word count formula
  (7.02.6); method 1 (pilot test) records under 9.02.2(2)(i) are absent
  by design because no pilot testing is performed.
- Videos are retained in object storage under the keys listed in each
  lesson's `video.txt`; they are included in the zip only when the export
  requested them.
- `bundle.json` lists every file with its sha256 and byte size.
"""


def create_export(
    db: Session,
    storage: Storage,
    course: Course,
    generated_by: Account,
    include_video: bool = False,
) -> AuditExport:
    """Build, store, and log one export. The stored zip is never touched
    again; a later generation adds a new row and a new key."""
    content, manifest = build(db, storage, course, generated_by, include_video)
    generated_at = datetime.fromisoformat(manifest["generated_at"])
    key = f"audits/{course.course_code}/{generated_at:%Y%m%dT%H%M%S%fZ}.zip"
    storage.put(key, io.BytesIO(content))
    export = AuditExport(
        course_id=course.id,
        generated_at=generated_at,
        generated_by_account_id=generated_by.id,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        storage_key=key,
    )
    db.add(export)
    db.commit()
    return export


def list_exports(db: Session, course: Course) -> list[AuditExport]:
    """Newest first."""
    return list(
        db.scalars(
            select(AuditExport)
            .where(AuditExport.course_id == course.id)
            .order_by(AuditExport.generated_at.desc(), AuditExport.id.desc())
        )
    )
