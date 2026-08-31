"""Readiness checklist: what stands between a course and publishing.

`check` only reports — with two exceptions: `courses.publish` refuses while
any block finding exists (the 008 publish gate), and `assessment.start`
refuses while any block finding outside PUBLISH_ONLY_CODES exists, because
an assessment that does not satisfy 6.01.2 is not a qualified assessment.
006 contributed the credit and 5.01.2.1 review-question findings; 007 the
6.01.2 assessment findings; 008 the development-and-review findings.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.assessment import OBJECTIVE_COVERAGE_PCT
from app.constants.participation import (
    CPA_PARTICIPATION_FIELDS,
    CPA_QUALIFYING_CREDENTIALS,
    TAX_PARTICIPATION_FIELDS,
    TAX_QUALIFYING_CREDENTIALS,
)
from app.constants.question_minimums import (
    COUNTING_MIN_CHOICES,
    MIN_CHOICES_ASSESSMENT,
    required_assessment_questions,
    required_review_questions,
)
from app.models.course import Course
from app.services import courses as courses_service
from app.services import credit
from app.services import development
from app.services import questions as questions_service

# The 008 findings gate publish, not the assessment: an admin previews a
# draft course's assessment before a developer or review is recorded, and
# none of these make the assessment less qualified under 6.01.2.
PUBLISH_ONLY_CODES = frozenset(
    {
        "developer_missing",
        "review_missing",
        "reviewer_is_developer",
        "cpa_participation",
        "description_missing",
    }
)


@dataclass
class Finding:
    code: str
    level: str  # "block" | "warn"
    message: str


def launch_findings(db: Session) -> list[Finding]:
    """What stands between the sponsor and opening the site — distinct
    from publish findings: a course may publish without these, but the
    site should not open (8.01.1 requires the policies "formalized,
    published, and made available" before participants arrive). Block
    findings here are exactly what `site.site_open_blockers` refuses the
    open flip with; warn findings are reported beside them."""
    from app.config import EMAIL_VARS, settings
    from app.constants.evaluation import EVALUATION_REVIEW_DAYS
    from app.services import courses as courses_module
    from app.services import disclosure
    from app.services import evaluations as evaluations_service
    from app.services import policies as policies_service

    findings: list[Finding] = []
    # 017: a site that is open but cannot send verification email has a
    # registration form that lies. The console backend is never enough to
    # open; dev/test flips satisfy this with dummy SMTP config, not by
    # weakening it.
    if not (settings.email_backend == "smtp" and settings.email_configured):
        missing = [
            var for var in EMAIL_VARS if not getattr(settings, var.lower())
        ]
        detail = (
            f"EMAIL_BACKEND is '{settings.email_backend}'"
            + (f" and {', '.join(missing)} unset" if missing else "")
        )
        findings.append(
            Finding(
                code="email_not_configured",
                level="block",
                message=(
                    "Outbound email is not configured for production "
                    f"({detail}); an open site must be able to send "
                    "verification email (017). Set EMAIL_BACKEND=smtp "
                    "with complete EMAIL_* settings."
                ),
            )
        )
    item_of = {"registration": 8, "refund": 9, "complaint": 10}
    for kind in policies_service.missing_kinds(db):
        findings.append(
            Finding(
                code="policy_missing",
                level="block",
                message=(
                    f"{policies_service.KIND_LABELS[kind]} policy not "
                    f"published (8.01 item {item_of[kind]}); 8.01.1 requires "
                    "policies formalized, published, and made available."
                ),
            )
        )
    # 016: opening onto an empty or non-compliant catalog is opening onto
    # nothing — at least one published course must disclose every
    # applicable 8.01 item. Only possible in dev (the publish gate refuses
    # incomplete disclosure), but the flip must not assume that.
    published = courses_module.list_published(db)
    incomplete = {
        course.course_code: disclosure.missing_items(db, course)
        for course in published
    }
    if not any(not items for items in incomplete.values()):
        if not published:
            findings.append(
                Finding(
                    code="catalog_empty",
                    level="block",
                    message=(
                        "No course is published; opening the site would "
                        "open onto an empty catalog, with no 8.01 "
                        "descriptive materials to make available."
                    ),
                )
            )
        for course_code, items in incomplete.items():
            findings.append(
                Finding(
                    code="catalog_undisclosable",
                    level="block",
                    message=(
                        f"{course_code} is published but cannot disclose "
                        + "; ".join(
                            f"8.01 item {item.number} ({item.name}): "
                            f"{item.reason}"
                            for item in items
                        )
                        + " — no published course discloses completely."
                    ),
                )
            )
    for course in courses_module.list_courses(db):
        due = evaluations_service.review_due(db, course)
        if due is not None:
            findings.append(
                Finding(
                    code="evaluation_review_due",
                    level="warn",
                    message=_evaluation_review_message(
                        course.course_code, due, EVALUATION_REVIEW_DAYS
                    ),
                )
            )
    return findings


def _evaluation_review_message(
    course_code: str, due: dict, review_days: int
) -> str:
    return (
        f"{course_code}: {due['unreviewed']} evaluation(s) unreviewed, the "
        f"oldest submitted {due['oldest_submitted_at'].date().isoformat()}, "
        f"more than {review_days} days ago. 4.04.2 requires periodic review "
        f"of evaluation results ({review_days} days is superCPE's own "
        "interval)."
    )


def sponsor_findings(db: Session) -> list[Finding]:
    """Sponsor-level findings, not tied to any one course. Today just
    `certificates_overdue`: 9.01 expects the certificate "as soon as
    possible" and within 60 days, and a completion older than that with no
    rendered PDF means the sponsor's paperwork is holding up a
    participant's earned credit."""
    from app.constants.enrollment import CERTIFICATE_DEADLINE_DAYS
    from app.services import completions as completions_service

    findings: list[Finding] = []
    overdue = completions_service.overdue(db)
    if overdue:
        named = ", ".join(
            f"{c.certificate_number} (completed "
            f"{c.completed_at.date().isoformat()})"
            for c in overdue
        )
        findings.append(
            Finding(
                code="certificates_overdue",
                level="warn",
                message=(
                    f"{len(overdue)} completion(s) older than "
                    f"{CERTIFICATE_DEADLINE_DAYS} days have no rendered "
                    f"certificate: {named}. 9.01 expects delivery within "
                    f"{CERTIFICATE_DEADLINE_DAYS} days."
                ),
            )
        )
    return findings


@dataclass
class ReviewCounts:
    """The 5.01.2.1 comparison, also shown when it is satisfied and no
    finding exists. `required` is None while the credit is stale: without a
    credit there is nothing to derive the requirement from."""

    counting: int
    required: int | None


def review_counts(db: Session, course: Course) -> ReviewCounts:
    counting = sum(
        1
        for q in questions_service.course_review_questions(db, course)
        if questions_service.counts_toward_minimum(q)
    )
    required = (
        required_review_questions(course.credit_award)
        if not credit.is_stale(course)
        else None
    )
    return ReviewCounts(counting=counting, required=required)


def check(db: Session, course: Course) -> list[Finding]:
    findings: list[Finding] = []

    fresh_credit = not credit.is_stale(course)
    if not fresh_credit:
        findings.append(
            Finding(
                code="credit_missing",
                level="block",
                message=(
                    "The course has no fresh credit measurement "
                    f"({credit.stale_reason(course)}); the review question "
                    "minimum cannot be checked without one."
                ),
            )
        )

    review_questions = questions_service.course_review_questions(db, course)
    counting = [
        q for q in review_questions if questions_service.counts_toward_minimum(q)
    ]

    if fresh_credit:
        required = required_review_questions(course.credit_award)
        if len(counting) < required:
            findings.append(
                Finding(
                    code="review_minimum",
                    level="block",
                    message=(
                        f"{len(counting)} counting review questions, but "
                        f"{required} are required for {course.credit_award} "
                        "CPE credit (5.01.2.1)."
                    ),
                )
            )

    # 5.01.2.1 requires review questions "throughout the program"; a lesson
    # with none cannot satisfy that, however many its neighbors carry.
    question_counts = {
        lesson.package_id: 0 for lesson in course.lessons
    }
    for question in review_questions:
        question_counts[question.package_id] += 1
    empty = [
        lesson.package.lesson_id
        for lesson in sorted(course.lessons, key=lambda cl: cl.position)
        if question_counts[lesson.package_id] == 0
    ]
    if empty:
        findings.append(
            Finding(
                code="review_placement",
                level="warn",
                message=(
                    "Lessons with no review question at all: "
                    f"{', '.join(empty)}. 5.01.2.1 places review questions "
                    "throughout the program."
                ),
            )
        )

    two_choice = [
        q.question_key
        for q in review_questions
        if len(q.choices) < COUNTING_MIN_CHOICES
    ]
    if two_choice:
        findings.append(
            Finding(
                code="review_two_choice",
                level="warn",
                message=(
                    "Two-choice review questions do not count toward the "
                    f"5.01.2.1 minimum: {', '.join(two_choice)}."
                ),
            )
        )

    findings += _assessment_findings(db, course, fresh_credit, review_questions)
    findings += _development_findings(course)
    findings += _evaluation_findings(db, course)

    return findings


def _evaluation_findings(db: Session, course: Course) -> list[Finding]:
    """The 4.04.2 warn finding: evaluations have waited longer than
    EVALUATION_REVIEW_DAYS without a recorded review of results.
    "Periodically" made concrete and reported, not enforced — never a
    block, because the fix (record a review) has nothing to do with the
    course's content."""
    from app.constants.evaluation import EVALUATION_REVIEW_DAYS
    from app.services import evaluations as evaluations_service

    due = evaluations_service.review_due(db, course)
    if due is None:
        return []
    return [
        Finding(
            code="evaluation_review_due",
            level="warn",
            message=_evaluation_review_message(
                course.course_code, due, EVALUATION_REVIEW_DAYS
            ),
        )
    ]


def _assessment_findings(
    db: Session, course: Course, fresh_credit: bool, review_questions
) -> list[Finding]:
    """The 6.01.2 findings: question minimum, forced choice, duplicates,
    and objective coverage. All block: an assessment that fails any of them
    is not a qualified assessment."""
    findings: list[Finding] = []
    lesson_of = {cl.package_id: cl.package.lesson_id for cl in course.lessons}
    assessment_questions = questions_service.course_assessment_questions(
        db, course
    )

    counting = [
        q
        for q in assessment_questions
        if len(q.choices) >= MIN_CHOICES_ASSESSMENT
    ]
    if fresh_credit:
        required = required_assessment_questions(course.credit_award)
        if len(counting) < required:
            findings.append(
                Finding(
                    code="assessment_minimum",
                    level="block",
                    message=(
                        f"{len(counting)} assessment questions, but "
                        f"{required} are required for {course.credit_award} "
                        "CPE credit (6.01.2)."
                    ),
                )
            )

    # Ingest already refuses two-choice questions of any kind, so this can
    # only arise from a fixture or a bypassed validator; kept as defense in
    # depth because 6.01.2 forbids forced choice outright.
    forced = [
        f"{q.question_key} ({lesson_of[q.package_id]})"
        for q in assessment_questions
        if len(q.choices) < MIN_CHOICES_ASSESSMENT
    ]
    if forced:
        findings.append(
            Finding(
                code="assessment_forced_choice",
                level="block",
                message=(
                    "Forced-choice questions are not permissible on the "
                    f"qualified assessment (6.01.2): {', '.join(forced)}."
                ),
            )
        )

    review_stems = {}
    for q in review_questions:
        review_stems.setdefault(questions_service.normalized_stem(q.stem), q)
    duplicates = []
    for q in assessment_questions:
        twin = review_stems.get(questions_service.normalized_stem(q.stem))
        if twin is not None:
            duplicates.append(
                f"assessment {q.question_key} ({lesson_of[q.package_id]}) "
                f"duplicates review {twin.question_key} "
                f"({lesson_of[twin.package_id]})"
            )
    if duplicates:
        findings.append(
            Finding(
                code="assessment_duplicate",
                level="block",
                message=(
                    "Duplicate review and assessment questions are not "
                    f"allowed (6.01.2): {'; '.join(duplicates)}."
                ),
            )
        )

    # Objective ids are unique only within a package, so coverage is keyed
    # by (package_id, objective id).
    all_objectives = {
        (group["package_id"], objective["id"]): group["lesson_id"]
        for group in courses_service.course_objectives(course)
        for objective in group["objectives"]
    }
    covered = {
        (q.package_id, key)
        for q in assessment_questions
        for key in q.objective_keys
        if (q.package_id, key) in all_objectives
    }
    if all_objectives:
        coverage_pct = Decimal(len(covered) * 100) / len(all_objectives)
        if coverage_pct < OBJECTIVE_COVERAGE_PCT:
            uncovered = [
                f"{key} ({lesson_id})"
                for (package_id, key), lesson_id in all_objectives.items()
                if (package_id, key) not in covered
            ]
            findings.append(
                Finding(
                    code="objective_coverage",
                    level="block",
                    message=(
                        f"The assessment measures {len(covered)} of "
                        f"{len(all_objectives)} learning objectives; 6.01.2 "
                        f"requires at least {OBJECTIVE_COVERAGE_PCT} "
                        "percent. Uncovered: "
                        f"{', '.join(uncovered)}."
                    ),
                )
            )

    return findings


def _qualifies(sme, credentials: frozenset) -> bool:
    return (
        sme is not None
        and sme.credential_type in credentials
        and sme.license_status == "active"
    )


def _development_findings(course: Course) -> list[Finding]:
    """The 4.01/4.01.1/4.02 findings plus the 8.01 description check. All
    block except review_due: block findings arise only from content and
    review facts, so an overdue course can still be unpublished and
    republished after a fresh review, which is the fix."""
    findings: list[Finding] = []

    if course.developer_id is None:
        findings.append(
            Finding(
                code="developer_missing",
                level="block",
                message=(
                    "The course names no developer; 4.01.1 requires "
                    "development by a subject matter expert."
                ),
            )
        )

    current = development.current_review(course)
    if current is None:
        latest_approved = next(
            (
                r
                for r in development.sorted_reviews(course)
                if r.decision == "approved"
            ),
            None,
        )
        if latest_approved is None:
            message = (
                "No approved review is recorded; 4.02 requires review by a "
                "content reviewer other than the developer before first "
                "presentation."
            )
        else:
            message = (
                "The content changed at "
                f"{course.content_updated_at.isoformat()}, after the last "
                "approved review, which reviewed the content as of "
                f"{latest_approved.content_updated_at_reviewed.isoformat()}; "
                "4.02 requires review again after each significant revision."
            )
        findings.append(
            Finding(code="review_missing", level="block", message=message)
        )
    elif (
        course.developer_id is not None
        and current.reviewer_id == course.developer_id
    ):
        findings.append(
            Finding(
                code="reviewer_is_developer",
                level="block",
                message=(
                    f"The current review's reviewer, {current.reviewer.name}, "
                    "is also the course developer; 4.02 requires content "
                    "reviewers other than those who developed the program."
                ),
            )
        )

    participants = [course.developer, current.reviewer if current else None]
    if course.field_of_study in CPA_PARTICIPATION_FIELDS and not any(
        _qualifies(p, CPA_QUALIFYING_CREDENTIALS) for p in participants
    ):
        findings.append(
            Finding(
                code="cpa_participation",
                level="block",
                message=(
                    f"field_of_study is {course.field_of_study} and neither "
                    "the developer nor the reviewer is a CPA with an active "
                    "license; 4.02 requires the participation of at least "
                    "one licensed CPA in every accounting or auditing "
                    "program."
                ),
            )
        )
    if course.field_of_study in TAX_PARTICIPATION_FIELDS and not any(
        _qualifies(p, TAX_QUALIFYING_CREDENTIALS) for p in participants
    ):
        findings.append(
            Finding(
                code="cpa_participation",
                level="block",
                message=(
                    f"field_of_study is {course.field_of_study} and neither "
                    "the developer nor the reviewer is a CPA, tax attorney, "
                    "or enrolled agent with an active license; 4.02 requires "
                    "the participation of at least one in every taxes "
                    "program."
                ),
            )
        )

    if not course.description.strip():
        findings.append(
            Finding(
                code="description_missing",
                level="block",
                message=(
                    "The course description is blank; it is the 8.01 course "
                    "announcement a participant reads before enrolling."
                ),
            )
        )

    due = development.review_due_at(course)
    if due is not None and due < date.today():
        findings.append(
            Finding(
                code="review_due",
                level="warn",
                message=(
                    f"The current review of {current.reviewed_at.isoformat()} "
                    f"came due {due.isoformat()} on the {course.review_cycle} "
                    "cycle; 4.01 requires review at least "
                    + (
                        "once a year."
                        if course.review_cycle == "annual"
                        else "every two years."
                    )
                ),
            )
        )

    return findings
