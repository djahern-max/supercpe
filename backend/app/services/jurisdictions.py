"""Per-jurisdiction credit policy (020).

7.01 measures credit in 50-minute periods but leaves boards of
accountancy free to differ "on acceptable increments of CPE credit", and
puts the check on the claiming CPA: they "should refer to the respective
state board requirements". This module is superCPE doing part of that
lookup — surfacing what the admin verified, on a date, against a named
source — never speaking for a board. Nothing here reads or writes a
stored credit: the 005 award is an input, and the round-down for a
coarser board is computed per request and labeled as computed.
"""

from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.credit import MIN_AWARDABLE
from app.constants.fields_of_study import FIELDS_OF_STUDY
from app.constants.jurisdiction_policy import (
    CREDIT_INCREMENT_STEPS,
    CREDIT_INCREMENTS,
    VERIFIED_STALE_MONTHS,
)
from app.constants.jurisdictions import US_JURISDICTIONS
from app.models.course import Course
from app.models.jurisdiction import JurisdictionPolicy


class JurisdictionRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def get(db: Session, code: str) -> JurisdictionPolicy | None:
    return db.scalar(
        select(JurisdictionPolicy).where(
            JurisdictionPolicy.jurisdiction == code
        )
    )


def all_rows(db: Session) -> dict[str, JurisdictionPolicy]:
    rows = db.scalars(select(JurisdictionPolicy))
    return {row.jurisdiction: row for row in rows}


def upsert(
    db: Session,
    code: str,
    credit_increment: str,
    non_technical_cap_note: str,
    source: str,
    verified_on: date | None,
    notes: str,
) -> JurisdictionPolicy:
    """Create-on-edit: the table ships empty and a row appears the first
    time the admin saves one, so an increment can never exist without an
    edit that chose it."""
    errors = []
    if code not in US_JURISDICTIONS:
        errors.append(
            f'"{code}" is not a two-letter US licensing jurisdiction code'
        )
    if credit_increment not in CREDIT_INCREMENTS:
        errors.append(
            f'credit_increment must be one of {", ".join(CREDIT_INCREMENTS)}'
        )
    if verified_on is not None and verified_on > date.today():
        errors.append("verified_on cannot be in the future")
    if errors:
        raise JurisdictionRuleViolation(errors)

    row = get(db, code)
    if row is None:
        row = JurisdictionPolicy(jurisdiction=code)
        db.add(row)
    row.credit_increment = credit_increment
    row.non_technical_cap_note = non_technical_cap_note.strip()
    row.source = source.strip()
    row.verified_on = verified_on
    row.notes = notes.strip()
    db.commit()
    return row


def displayable(row: JurisdictionPolicy | None) -> bool:
    """A fact reaches a participant only when the admin verified it: a
    known increment, a named source, and the date it was checked."""
    return (
        row is not None
        and row.credit_increment != "unknown"
        and bool(row.source.strip())
        and row.verified_on is not None
    )


def verification_stale(row: JurisdictionPolicy) -> bool:
    """The admin-only re-verification nudge; approximate months are fine
    for a nudge."""
    if row.verified_on is None:
        return False
    return date.today() - row.verified_on > timedelta(
        days=VERIFIED_STALE_MONTHS * 31
    )


def board_rounded(credit: Decimal, credit_increment: str) -> Decimal | None:
    """The 005 award rounded down — never half-up — to a board's coarser
    increment (7.01.1's arithmetic: 1.4 under one-half is 1.0). None when
    the board accepts one-fifth: the stored award is already in one-fifth
    increments, so there is nothing to compute."""
    step = CREDIT_INCREMENT_STEPS[credit_increment]
    if step is None or credit_increment == "one_fifth":
        return None
    steps = (credit / step).to_integral_value(rounding=ROUND_FLOOR)
    return (steps * step).quantize(Decimal("0.1"))


def note_for(
    db: Session, state: str | None, course: Course
) -> dict | None:
    """The jurisdiction hint for one participant and one course, or None
    when there is nothing verified to say. The caller has already decided
    the course is publicly renderable; this never touches the course row.
    """
    if not state:
        return None
    # Mirrors credit.public_credit: no award a participant is shown means
    # no hint either.
    if course.credit_award is None or course.credit_award < MIN_AWARDABLE:
        return None
    row = get(db, state)
    if not displayable(row):
        return None
    # A course whose field is unknown to the 2024 list gets no
    # classification and no hint at all.
    technical = FIELDS_OF_STUDY.get(course.field_of_study)
    if technical is None:
        return None
    rounded = board_rounded(course.credit_award, row.credit_increment)
    cap_note = row.non_technical_cap_note.strip()
    return {
        "jurisdiction": row.jurisdiction,
        "jurisdiction_name": US_JURISDICTIONS[row.jurisdiction],
        "credit_increment": row.credit_increment,
        "recommended_credit": str(course.credit_award),
        "board_rounded_credit": str(rounded) if rounded is not None else None,
        # Quoted only when the course's field is non-technical; a cap on
        # non-technical hours says nothing about an Accounting course.
        "non_technical_cap_note": cap_note
        if technical is False and cap_note
        else None,
        "verified_on": row.verified_on,
    }
