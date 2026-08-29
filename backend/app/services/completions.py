"""The completion record and the 9.01 certificate snapshot.

`create` runs inside the passing submit's transaction (it flushes, never
commits): a completion exists if and only if the submit that earned it
committed. Every certificate-bearing fact is copied from the rows as they
stand at completion and never re-read (ROADMAP structural difference 4);
`certificate_snapshot` is the certificate, and `render` reads it alone.

Issuance is separate from completion: if the sponsor's issuance fields are
blank when a participant completes, the 9.02.2(1) record is still written
and the snapshot still frozen — only the PDF waits (`ensure_rendered`),
and `certificates_overdue` reports it after 60 days.
"""

import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.certificate import (
    ISSUANCE_SPONSOR_FIELDS,
    PROGRAM_TYPE,
    TIME_STATEMENT,
)
from app.constants.credit import CREDIT_BASIS
from app.constants.enrollment import CERTIFICATE_DEADLINE_DAYS
from app.models.attempt import Attempt
from app.models.enrollment import CertificateSequence, Completion, Enrollment
from app.models.sponsor import SponsorProfile
from app.services import certificates, credit, development
from app.services import sponsor as sponsor_service
from app.storage import Storage


class CreditStale(Exception):
    """The course's credit measurement is stale at the moment of completion.
    Cannot happen on a published course (publish gates on fresh credit and
    published content is immutable); kept as defense in depth, mapped to a
    409 by the router."""

    def __init__(self, reason: str):
        self.errors = [
            "the course's credit measurement is stale "
            f"({reason}); the completion cannot record a credit that is not "
            "current"
        ]
        super().__init__(self.errors[0])


class IssuanceBlocked(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        self.errors = [
            "the certificate cannot be rendered while sponsor fields are "
            f"blank: {', '.join(missing)}"
        ]
        super().__init__(self.errors[0])


def _next_certificate_number(db: Session, year: int) -> str:
    """YYYY-NNNNNN from the per-year counter, read with a row lock so two
    simultaneous passes cannot mint the same number."""
    sequence = db.get(CertificateSequence, year, with_for_update=True)
    if sequence is None:
        sequence = CertificateSequence(year=year, last_number=0)
        db.add(sequence)
        db.flush()
    sequence.last_number += 1
    return f"{year}-{sequence.last_number:06d}"


def _person(sme) -> dict | None:
    if sme is None:
        return None
    return {"name": sme.name, "credentials": sme.credentials}


def create(db: Session, enrollment: Enrollment, attempt: Attempt) -> Completion:
    """Build the completion and its snapshot from the live rows as they
    stand now. Flushes only; the caller (the passing submit) owns the
    transaction."""
    course = enrollment.course
    if credit.is_stale(course):
        raise CreditStale(credit.stale_reason(course))

    # Read, never create: get_profile commits, which would break the
    # submit transaction. An absent row (create_all test databases) reads
    # as an all-blank profile.
    profile = db.get(SponsorProfile, 1)
    may_claim = profile.may_claim_registry if profile else False
    registrations = sponsor_service.get_state_registrations(db)
    current_review = development.current_review(course)
    account = enrollment.account

    completed_at = attempt.submitted_at
    certificate_number = _next_certificate_number(db, completed_at.year)
    verification_token = secrets.token_hex(32)

    snapshot = {
        "sponsor_name": profile.name if profile else "",  # 9.01 item 1
        "sponsor_legal_name": profile.legal_name if profile else "",  # 9.01.1
        "participant_name": account.display_name,  # item 2
        "participant_email": account.email,
        "course_title": course.title,  # item 3
        "course_code": course.course_code,
        "completed_at": completed_at.isoformat(),  # item 4
        "location": None,  # item 5: self study, printed as not applicable
        "program_type": PROGRAM_TYPE,  # item 6
        "credit": str(course.credit_award),  # item 7, as text, one decimal
        "field_of_study": course.field_of_study,  # item 7
        # Item 8: present only if the sponsor may claim Registry membership
        # at this moment; flipping the status later changes nothing.
        "national_registry_id": (
            profile.national_registry_id if profile and may_claim else None
        ),
        "state_registrations": [  # item 9
            {"state": row.state, "number": row.registration_number}
            for row in registrations
        ],
        "time_statement": TIME_STATEMENT,  # item 10
        "other_statements": [  # item 11
            line.strip()
            for line in (
                profile.other_certificate_statements if profile else ""
            ).splitlines()
            if line.strip()
        ],
        "knowledge_level": course.knowledge_level,
        "package_versions": enrollment.package_versions,
        "passing_pct": str(attempt.passing_pct),
        "score_pct": str(attempt.score_pct),
        "recommended_credit_basis": CREDIT_BASIS,
        "developed_by": _person(course.developer),
        "reviewed_by": _person(current_review.reviewer if current_review else None),
        "certificate_number": certificate_number,
        "verification_token": verification_token,
        "snapshot_version": 1,
    }

    completion = Completion(
        enrollment_id=enrollment.id,
        attempt_id=attempt.id,
        completed_at=completed_at,
        credit_awarded=course.credit_award,
        field_of_study=course.field_of_study,
        certificate_number=certificate_number,
        verification_token=verification_token,
        certificate_snapshot=snapshot,
    )
    db.add(completion)
    db.flush()
    return completion


def get(db: Session, completion_id: int) -> Completion | None:
    return db.get(Completion, completion_id)


def missing_for_issuance(db: Session) -> list[str]:
    """The live sponsor fields still blocking a render. Deliberately read
    live, not from the snapshot: the render gate is the sponsor's paperwork
    today, while what prints is the snapshot from completion time."""
    profile = db.get(SponsorProfile, 1)
    if profile is None:
        return list(ISSUANCE_SPONSOR_FIELDS)
    return profile.missing_fields(for_issuance=True)


def certificate_ready(db: Session, completion: Completion) -> bool:
    return completion.certificate_key is not None or not missing_for_issuance(db)


def ensure_rendered(db: Session, storage: Storage, completion: Completion) -> Completion:
    """Render and store the certificate once. The first render's key and
    timestamp are the only fields of a completion that are ever set after
    creation; a completion that already has them is returned untouched."""
    if completion.certificate_key is not None:
        return completion
    missing = missing_for_issuance(db)
    if missing:
        raise IssuanceBlocked(missing)
    pdf = certificates.render(completion.certificate_snapshot)
    key = f"certificates/{completion.certificate_number}.pdf"
    storage.put(key, BytesIO(pdf))
    completion.certificate_key = key
    completion.certificate_rendered_at = datetime.now(timezone.utc)
    db.commit()
    return completion


def overdue(db: Session) -> list[Completion]:
    """Completions past the 9.01 60-day delivery expectation with no
    rendered certificate — the safety net behind snapshot-at-completion."""
    deadline = datetime.now(timezone.utc) - timedelta(
        days=CERTIFICATE_DEADLINE_DAYS
    )
    return list(
        db.scalars(
            select(Completion)
            .where(
                Completion.certificate_rendered_at.is_(None),
                Completion.completed_at < deadline,
            )
            .order_by(Completion.completed_at)
        )
    )
