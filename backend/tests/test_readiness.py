"""Feature 006: the readiness checklist (reported, never refused here;
008 turns block findings into a publish refusal)."""

from app.services import credit, questions, readiness
from tests.test_credit import make_course_row, make_package_row
from tests.test_questions import make_question, questions_of


def normalize(db, package):
    rows = questions.normalize(db, package)
    db.commit()
    return rows


def finding(findings, code):
    matches = [f for f in findings if f.code == code]
    return matches[0] if matches else None


def test_credit_missing_blocks(db_session):
    package = make_package_row(db_session, questions=questions_of(review=3))
    normalize(db_session, package)
    course = make_course_row(db_session, "GOLD", package)
    # No credit.store: the course has never had its credit computed.
    findings = readiness.check(db_session, course)
    missing = finding(findings, "credit_missing")
    assert missing is not None
    assert missing.level == "block"
    # Without a credit there is no required count to compare against.
    assert finding(findings, "review_minimum") is None


def test_review_minimum_reports_both_numbers(db_session):
    # 2820 s all-video + 2 questions x 1.85 = 50.70 min -> 1.014 -> 1.0
    # credit, which 5.01.2.1 says needs 3 review questions; only 2 exist.
    package = make_package_row(
        db_session, duration_seconds=2820, questions=questions_of(review=2)
    )
    normalize(db_session, package)
    course = make_course_row(db_session, "GOLD", package)
    credit.store(db_session, course.id)
    db_session.refresh(course)

    findings = readiness.check(db_session, course)
    assert finding(findings, "credit_missing") is None
    minimum = finding(findings, "review_minimum")
    assert minimum is not None
    assert minimum.level == "block"
    assert "2" in minimum.message
    assert "3" in minimum.message
    assert "1.0" in minimum.message


def test_two_choice_review_question_does_not_count(db_session):
    two_choice = make_question(9, "review", choices=2)
    package = make_package_row(
        db_session,
        duration_seconds=2820,
        questions=questions_of(review=2) + [two_choice],
    )
    normalize(db_session, package)
    course = make_course_row(db_session, "GOLD", package)
    credit.store(db_session, course.id)
    db_session.refresh(course)

    findings = readiness.check(db_session, course)
    # Three review questions exist, but the two-choice one does not count:
    # still 2 of 3, still blocked, plus the warning naming the question.
    minimum = finding(findings, "review_minimum")
    assert minimum is not None
    assert "2" in minimum.message
    warn = finding(findings, "review_two_choice")
    assert warn is not None
    assert warn.level == "warn"
    assert "q-review-9" in warn.message


def test_lesson_without_review_questions_warns_placement(db_session):
    with_questions = make_package_row(
        db_session, lesson_id="GOLD-01", questions=questions_of(review=3)
    )
    without = make_package_row(
        db_session, lesson_id="GOLD-02", questions=questions_of(assessment=1)
    )
    normalize(db_session, with_questions)
    normalize(db_session, without)
    course = make_course_row(db_session, "GOLD", with_questions, without)
    credit.store(db_session, course.id)
    db_session.refresh(course)

    findings = readiness.check(db_session, course)
    placement = finding(findings, "review_placement")
    assert placement is not None
    assert placement.level == "warn"
    assert "GOLD-02" in placement.message
    assert "GOLD-01" not in placement.message


def test_satisfied_course_has_no_review_findings(db_session):
    package = make_package_row(
        db_session,
        duration_seconds=486,
        questions=questions_of(review=3, assessment=2),
    )
    normalize(db_session, package)
    course = make_course_row(db_session, "GOLD", package)
    credit.store(db_session, course.id)
    db_session.refresh(course)

    # 486 s + 5 x 1.85 -> 17.35 min -> 0.347 -> 0.2 credit -> 0 review
    # questions required, 2 assessment questions required (both present,
    # covering the lone objective). The 008 development findings are out of
    # this test's scope: no developer or review exists here.
    findings = [
        f
        for f in readiness.check(db_session, course)
        if f.code not in readiness.PUBLISH_ONLY_CODES
    ]
    assert findings == []
    # The comparison is still reported even with nothing to find.
    counts = readiness.review_counts(db_session, course)
    assert counts.counting == 3
    assert counts.required == 0


def test_review_counts_without_credit(db_session):
    package = make_package_row(db_session, questions=questions_of(review=2))
    normalize(db_session, package)
    course = make_course_row(db_session, "GOLD", package)
    counts = readiness.review_counts(db_session, course)
    assert counts.counting == 2
    assert counts.required is None
