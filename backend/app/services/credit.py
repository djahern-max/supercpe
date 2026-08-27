"""Method 2 credit measurement: the 7.02.6 word count formula.

    [(words / 180) + actual A/V minutes + (questions x 1.85)] / 50 = credit

Every input is read from the stored lesson packages, never typed: durations
are the ffprobe-measured ones from 002 (7.02.7 requires actual duration), a
segment contributes either its A/V time or its words per the manifest's
`av_is_additional_learning` (7.02.7), and every stored question counts
(7.02.6). Everything that reaches a stored credit is `Decimal` or int.

Pure and read-only except `store`. `store` deliberately does not call
`touch`: computing credit is not a content change, and bumping
`content_updated_at` here would make every stored credit instantly stale.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_FLOOR, Decimal

from sqlalchemy.orm import Session

from app.constants.credit import (
    CREDIT_BASIS,
    CREDIT_FORMULA_VERSION,
    CREDIT_INCREMENT,
    MIN_AWARDABLE,
    MINUTES_PER_CREDIT,
    MINUTES_PER_QUESTION,
    WORDS_PER_MINUTE,
)
from app.models.course import Course

_SECONDS_PER_MINUTE = Decimal(60)

# The formula's terms are recorded to two decimal places of a minute so the
# 9.02.2(2)(ii) record re-adds exactly as written. Truncation (ROUND_DOWN)
# rather than rounding half up: a term can then only ever understate, so the
# record can never inflate a credit past a rounding boundary.
_MINUTES_2DP = Decimal("0.01")
_CREDIT_3DP = Decimal("0.001")


@dataclass
class CreditLessonRow:
    lesson_id: str
    package_id: int
    version: int
    position: int
    title: str
    duration_seconds: int
    av_is_additional_learning: bool
    av_seconds_counted: int
    word_count: int
    words_counted: int
    review_questions: int
    assessment_questions: int


@dataclass
class CreditBreakdown:
    course_code: str
    rows: list[CreditLessonRow]
    word_count: int  # total words counted across lessons
    av_seconds: int  # total A/V seconds counted across lessons
    question_count: int
    word_minutes: Decimal  # word_count / 180
    av_minutes: Decimal  # av_seconds as minutes
    question_minutes: Decimal  # question_count x 1.85
    raw_minutes: Decimal  # the numerator, before / 50
    raw_credit: Decimal  # raw_minutes / 50, before rounding
    award: Decimal  # rounded down to one-fifth
    formula_version: str


def _terms(
    word_count: int, av_seconds: int, question_count: int
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    word_minutes = (Decimal(word_count) / WORDS_PER_MINUTE).quantize(
        _MINUTES_2DP, rounding=ROUND_DOWN
    )
    av_minutes = (Decimal(av_seconds) / _SECONDS_PER_MINUTE).quantize(
        _MINUTES_2DP, rounding=ROUND_DOWN
    )
    question_minutes = (Decimal(question_count) * MINUTES_PER_QUESTION).quantize(
        _MINUTES_2DP, rounding=ROUND_DOWN
    )
    raw_minutes = word_minutes + av_minutes + question_minutes
    raw_credit = (raw_minutes / MINUTES_PER_CREDIT).quantize(
        _CREDIT_3DP, rounding=ROUND_DOWN
    )
    return word_minutes, av_minutes, question_minutes, raw_minutes, raw_credit


def round_down(raw: Decimal) -> Decimal:
    """floor(raw / 0.2) * 0.2 — one-fifth increments, never up (7.01, 7.02.6).

    State boards differ on acceptable increments of CPE credit (7.01);
    superCPE will need a per-jurisdiction increment policy (roadmap 019).
    One-fifth is the finest granularity the Standards permit for self study,
    and rounding down to it never overstates under any coarser policy.
    """
    if raw < MIN_AWARDABLE:
        return Decimal("0.0")
    steps = (raw / CREDIT_INCREMENT).to_integral_value(rounding=ROUND_FLOOR)
    return (steps * CREDIT_INCREMENT).quantize(Decimal("0.1"))


def compute(db: Session, course_id: int) -> CreditBreakdown:
    """Run the formula over the course's attached packages. Writes nothing."""
    course = db.get(Course, course_id)
    rows = []
    for lesson in sorted(course.lessons, key=lambda cl: cl.position):
        package = lesson.package
        # Every question counts: review questions, including those above the
        # minimum, and assessment questions (7.02.6). Features 006 and 007
        # must not narrow this to one kind.
        review = sum(1 for q in package.questions if q.get("kind") == "review")
        assessment = sum(
            1 for q in package.questions if q.get("kind") == "assessment"
        )
        # 7.02.7: A/V that is additional learning counts by its measured
        # duration; A/V that merely narrates the text counts by its words
        # instead, and the duration does not enter at all.
        if package.av_is_additional_learning:
            av_counted, words_counted = package.duration_seconds, 0
        else:
            av_counted, words_counted = 0, package.word_count
        rows.append(
            CreditLessonRow(
                lesson_id=package.lesson_id,
                package_id=package.id,
                version=package.version,
                position=lesson.position,
                title=package.title,
                duration_seconds=package.duration_seconds,
                av_is_additional_learning=package.av_is_additional_learning,
                av_seconds_counted=av_counted,
                word_count=package.word_count,
                words_counted=words_counted,
                review_questions=review,
                assessment_questions=assessment,
            )
        )

    word_count = sum(row.words_counted for row in rows)
    av_seconds = sum(row.av_seconds_counted for row in rows)
    question_count = sum(
        row.review_questions + row.assessment_questions for row in rows
    )
    word_minutes, av_minutes, question_minutes, raw_minutes, raw_credit = _terms(
        word_count, av_seconds, question_count
    )
    return CreditBreakdown(
        course_code=course.course_code,
        rows=rows,
        word_count=word_count,
        av_seconds=av_seconds,
        question_count=question_count,
        word_minutes=word_minutes,
        av_minutes=av_minutes,
        question_minutes=question_minutes,
        raw_minutes=raw_minutes,
        raw_credit=raw_credit,
        award=round_down(raw_minutes / MINUTES_PER_CREDIT),
        formula_version=CREDIT_FORMULA_VERSION,
    )


def store(db: Session, course_id: int) -> CreditBreakdown:
    breakdown = compute(db, course_id)
    course = db.get(Course, course_id)
    course.credit_award = breakdown.award
    course.credit_raw_minutes = breakdown.raw_minutes
    course.credit_word_count = breakdown.word_count
    course.credit_av_seconds = breakdown.av_seconds
    course.credit_question_count = breakdown.question_count
    course.credit_breakdown = [asdict(row) for row in breakdown.rows]
    course.credit_formula_version = breakdown.formula_version
    course.credit_computed_at = datetime.now(timezone.utc)
    db.commit()
    return breakdown


def is_stale(course: Course) -> bool:
    return (
        course.credit_computed_at is None
        or course.credit_computed_at < course.content_updated_at
        or course.credit_formula_version != CREDIT_FORMULA_VERSION
    )


def stale_reason(course: Course) -> str | None:
    if course.credit_computed_at is None:
        return "credit has never been computed"
    if course.credit_formula_version != CREDIT_FORMULA_VERSION:
        return (
            f"formula version changed ({course.credit_formula_version} -> "
            f"{CREDIT_FORMULA_VERSION})"
        )
    if course.credit_computed_at < course.content_updated_at:
        return "content changed since the credit was computed"
    return None


def from_stored(course: Course) -> CreditBreakdown | None:
    """Rebuild the breakdown from the stored columns, without recomputing
    from the packages. This is what 9.02.2(2)(ii) retains: the record stands
    on its own even after lessons change or detach."""
    if course.credit_computed_at is None:
        return None
    word_minutes, av_minutes, question_minutes, raw_minutes, raw_credit = _terms(
        course.credit_word_count,
        course.credit_av_seconds,
        course.credit_question_count,
    )
    return CreditBreakdown(
        course_code=course.course_code,
        rows=[CreditLessonRow(**row) for row in course.credit_breakdown],
        word_count=course.credit_word_count,
        av_seconds=course.credit_av_seconds,
        question_count=course.credit_question_count,
        word_minutes=word_minutes,
        av_minutes=av_minutes,
        question_minutes=question_minutes,
        raw_minutes=raw_minutes,
        raw_credit=raw_credit,
        award=Decimal(course.credit_award),
        formula_version=course.credit_formula_version,
    )


def public_credit(course: Course) -> tuple[str | None, str | None]:
    """(recommended_credit, credit_basis) for the 8.01 disclosure payload.

    Serves (None, None) rather than a stale number, and likewise when the
    award is below the minimum: a participant is never shown "0.0"."""
    if is_stale(course) or course.credit_award < MIN_AWARDABLE:
        return None, None
    return str(course.credit_award), CREDIT_BASIS


def as_text(breakdown: CreditBreakdown) -> str:
    """The calculation written out the way a reviewer would read it. Retained
    in the audit bundle (011) as the 9.02.2(2)(ii) "actual calculation"."""
    lines = [
        f"CPE credit calculation for course {breakdown.course_code}",
        "Method 2, word count formula (2026 Standards 7.02.6, 7.02.7)",
        f"Formula version: {breakdown.formula_version}",
        "",
        "Per lesson:",
    ]
    if not breakdown.rows:
        lines.append("  (no lessons attached)")
    for row in breakdown.rows:
        av_note = (
            f"{row.av_seconds_counted} s counted (additional learning)"
            if row.av_is_additional_learning
            else f"0 s counted ({row.duration_seconds} s narrates the text)"
        )
        lines += [
            f"  {row.position}. {row.lesson_id} v{row.version} — {row.title}",
            f"     audio/video: {av_note}",
            f"     words: {row.words_counted} counted",
            f"     questions: {row.review_questions} review + "
            f"{row.assessment_questions} assessment",
        ]
    lines += [
        "",
        "Totals:",
        f"  words counted:       {breakdown.word_count}",
        f"  A/V seconds counted: {breakdown.av_seconds}",
        f"  questions:           {breakdown.question_count}",
        "",
        "[(words / 180) + A/V minutes + (questions x 1.85)] / 50 = credit",
        f"  {breakdown.word_count} / {WORDS_PER_MINUTE} = "
        f"{breakdown.word_minutes} minutes",
        f"  {breakdown.av_seconds} s / 60 = {breakdown.av_minutes} minutes",
        f"  {breakdown.question_count} x {MINUTES_PER_QUESTION} = "
        f"{breakdown.question_minutes} minutes",
        f"  {breakdown.word_minutes} + {breakdown.av_minutes} + "
        f"{breakdown.question_minutes} = {breakdown.raw_minutes} minutes",
        f"  {breakdown.raw_minutes} / {MINUTES_PER_CREDIT} = "
        f"{breakdown.raw_credit} raw credit",
        f"Rounded down to one-fifth increments (7.01): {breakdown.award}",
        f"Recommended CPE credit: {breakdown.award}",
    ]
    return "\n".join(lines)
