"""Feature 010: assessment re-gating behind the enrollment, and the
completion record (6.01, 9.01, 9.02.2(1)).

The load-bearing tests: a completion exists only because a passing submit
created it in the same transaction, its snapshot carries every 9.01 item
frozen at that moment, and the failed-attempt payload through the
enrollment path is as silent as 007's (6.01.2 sub-ii).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.constants.assessment import RETAKES_ALLOWED
from app.models.enrollment import Completion
from app.services import assessment, enrollments
from app.services import sponsor as sponsor_service
from app.services.assessment import AssessmentRuleViolation
from tests.test_assessment import walk_asserting_no_feedback
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    answer_all_reviews,
    enroll,
    make_participant,
    make_published_course,
    setup_enrolled,
)

# The eleven 9.01 items as snapshot keys (5 is location, 11 the other
# statements), plus the 9.01.1 awarding entity.
NINE_OH_ONE_KEYS = (
    "sponsor_name",  # 1
    "sponsor_legal_name",  # 9.01.1
    "participant_name",  # 2
    "course_title",  # 3
    "completed_at",  # 4
    "location",  # 5
    "program_type",  # 6
    "credit",  # 7
    "field_of_study",  # 7
    "national_registry_id",  # 8
    "state_registrations",  # 9
    "time_statement",  # 10
    "other_statements",  # 11
)


def complete_profile(db):
    return sponsor_service.update_profile(
        db,
        {
            "name": "superCPE",
            "legal_name": "RYZE.AI LLC",
            "registry_status": "not_registered",
            "national_registry_id": "",
            "website": "https://supercpe.com",
            "contact_email": "hello@supercpe.com",
            "contact_phone": "555-0100",
            "address": "1 Main St, Portsmouth, NH",
            "other_certificate_statements": "Retain this certificate.",
        },
    )


def expire(db, enrollment):
    enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()


def correct_answers(db, attempt, wrong=0):
    """The factory's correct choice is always 'a' (first)."""
    answers = {}
    for i, question in enumerate(assessment.questions_for_attempt(db, attempt)):
        chosen = (
            next(c for c in question.choices if not c.is_correct)
            if i < wrong
            else next(c for c in question.choices if c.is_correct)
        )
        answers[question.id] = chosen.id
    return answers


def sit(db, enrollment, wrong=0):
    attempt = assessment.start_for_enrollment(db, enrollment)
    return assessment.submit(db, attempt, correct_answers(db, attempt, wrong))


def make_completed(db, course_code="GOLD"):
    complete_profile(db)
    course, package = make_published_course(db, course_code)
    participant = make_participant(db)
    enrollment = enroll(db, course, participant)
    answer_all_reviews(db, enrollment)
    attempt = sit(db, enrollment)
    assert attempt.status == "passed"
    return course, enrollment, attempt


# --- start gating -----------------------------------------------------------


def test_start_refused_naming_unanswered_review_questions(db_session):
    course, _ = make_published_course(db_session)
    enrollment = enroll(db_session, course, make_participant(db_session))
    with pytest.raises(AssessmentRuleViolation) as exc:
        assessment.start_for_enrollment(db_session, enrollment)
    message = exc.value.errors[0]
    assert "q-review-0" in message and "q-review-1" in message
    assert "GOLD-01" in message


def test_start_refused_after_expiry(db_session):
    course, _ = make_published_course(db_session)
    enrollment = enroll(db_session, course, make_participant(db_session))
    answer_all_reviews(db_session, enrollment)
    expire(db_session, enrollment)
    with pytest.raises(AssessmentRuleViolation, match="expired"):
        assessment.start_for_enrollment(db_session, enrollment)


def test_start_refused_when_retakes_exhausted(db_session):
    course, _ = make_published_course(db_session)
    enrollment = enroll(db_session, course, make_participant(db_session))
    answer_all_reviews(db_session, enrollment)
    for _ in range(1 + RETAKES_ALLOWED):
        attempt = sit(db_session, enrollment, wrong=4)
        assert attempt.status == "failed"
    assert enrollments.retakes_remaining(db_session, enrollment) == 0
    with pytest.raises(AssessmentRuleViolation) as exc:
        assessment.start_for_enrollment(db_session, enrollment)
    assert str(RETAKES_ALLOWED) in exc.value.errors[0]
    assert "RETAKES_ALLOWED" in exc.value.errors[0]


def test_submit_after_expiry_abandons_the_attempt(db_session):
    course, _ = make_published_course(db_session)
    enrollment = enroll(db_session, course, make_participant(db_session))
    answer_all_reviews(db_session, enrollment)
    attempt = assessment.start_for_enrollment(db_session, enrollment)
    expire(db_session, enrollment)
    with pytest.raises(AssessmentRuleViolation, match="expired"):
        assessment.submit(
            db_session, attempt, correct_answers(db_session, attempt)
        )
    assert attempt.status == "failed"
    assert attempt.score_pct is None
    assert enrollment.completion is None


# --- the sub-ii rule through the enrollment path ----------------------------


def test_failed_enrollment_result_carries_no_feedback(client, db_session):
    _, package, enrollment = setup_enrolled(client, db_session)
    answer_all_reviews(db_session, enrollment)
    start = client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment/attempts"
    )
    assert start.status_code == 201, start.json()
    attempt_id = start.json()["attempt_id"]
    info = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment"
    ).json()
    answers = {
        str(q["question_id"]): q["choices"][1]["choice_id"]
        for q in info["questions"]
    }
    response = client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment/attempts"
        f"/{attempt_id}/submit",
        json={"answers": answers},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["retakes_allowed"] == RETAKES_ALLOWED
    assert body["retakes_remaining"] == RETAKES_ALLOWED
    walk_asserting_no_feedback(body)


# --- completion -------------------------------------------------------------


def test_passing_submit_creates_exactly_one_completion(db_session):
    course, enrollment, attempt = make_completed(db_session)
    [completion] = db_session.query(Completion).all()
    assert completion.enrollment_id == enrollment.id
    assert completion.attempt_id == attempt.id
    assert completion.credit_awarded == Decimal("0.4")
    assert completion.credit_awarded == course.credit_award
    assert completion.completed_at == attempt.submitted_at
    assert enrollments.status(enrollment) == "completed"

    # The certificate number is year-prefixed with a six-digit sequence.
    year = attempt.submitted_at.year
    assert completion.certificate_number == f"{year}-000001"
    assert len(completion.verification_token) == 64

    # A completed enrollment cannot sit again.
    answer_all_reviews(db_session, enrollment)
    with pytest.raises(AssessmentRuleViolation, match="completed"):
        assessment.start_for_enrollment(db_session, enrollment)


def test_second_completion_gets_the_next_number(db_session):
    _, _, attempt = make_completed(db_session)
    course2, _ = make_published_course(db_session, "SILVER")
    other = make_participant(db_session, "pat2@supercpe.test")
    enrollment2 = enroll(db_session, course2, other)
    answer_all_reviews(db_session, enrollment2)
    sit(db_session, enrollment2)
    numbers = sorted(
        row.certificate_number for row in db_session.query(Completion)
    )
    year = attempt.submitted_at.year
    assert numbers == [f"{year}-000001", f"{year}-000002"]


def test_snapshot_carries_all_eleven_items(db_session):
    _, enrollment, attempt = make_completed(db_session)
    snapshot = enrollment.completion.certificate_snapshot
    for key in NINE_OH_ONE_KEYS:
        assert key in snapshot, key
    assert snapshot["sponsor_name"] == "superCPE"
    assert snapshot["sponsor_legal_name"] == "RYZE.AI LLC"
    assert snapshot["participant_name"] == "Pat Smith"
    assert snapshot["course_title"] == "Course GOLD"
    assert snapshot["location"] is None
    assert snapshot["program_type"] == "Self study"
    assert snapshot["credit"] == "0.4"
    assert snapshot["field_of_study"] == "Accounting"
    assert snapshot["national_registry_id"] is None
    assert snapshot["time_statement"] == (
        "CPE credits have been granted based on a 50-minute hour."
    )
    assert snapshot["other_statements"] == ["Retain this certificate."]
    assert snapshot["developed_by"]["name"] == "Dev CPA"
    assert snapshot["reviewed_by"]["name"] == "Rev CPA"
    assert snapshot["package_versions"] == enrollment.package_versions
    assert snapshot["snapshot_version"] == 1


def test_snapshot_is_immutable_under_later_edits(db_session):
    from app.services import courses as courses_service

    course, enrollment, _ = make_completed(db_session)
    before = dict(enrollment.completion.certificate_snapshot)

    courses_service.unpublish(db_session, course)
    courses_service.update_course(db_session, course, title="Renamed Course")
    profile = sponsor_service.get_profile(db_session)
    profile.name = "renamedCPE"
    enrollment.account.display_name = "Renamed Person"
    db_session.commit()
    sponsor_service.set_state_registrations(
        db_session, [{"state": "NH", "registration_number": "999", "notes": ""}]
    )

    db_session.refresh(enrollment.completion)
    assert enrollment.completion.certificate_snapshot == before
    assert enrollment.completion.certificate_snapshot["course_title"] == "Course GOLD"
    assert enrollment.completion.certificate_snapshot["sponsor_name"] == "superCPE"
    assert (
        enrollment.completion.certificate_snapshot["participant_name"]
        == "Pat Smith"
    )
    assert enrollment.completion.certificate_snapshot["state_registrations"] == []


def test_item_8_reflects_registry_status_at_completion_only(db_session):
    # Not registered at completion: no item 8, and flipping later changes
    # nothing.
    _, enrollment, _ = make_completed(db_session)
    assert (
        enrollment.completion.certificate_snapshot["national_registry_id"]
        is None
    )
    profile = sponsor_service.get_profile(db_session)
    profile.registry_status = "registered"
    profile.national_registry_id = "112233"
    db_session.commit()
    db_session.refresh(enrollment.completion)
    assert (
        enrollment.completion.certificate_snapshot["national_registry_id"]
        is None
    )

    # Registered at completion: item 8 is in the snapshot.
    course2, _ = make_published_course(db_session, "SILVER")
    other = make_participant(db_session, "pat2@supercpe.test")
    enrollment2 = enroll(db_session, course2, other)
    answer_all_reviews(db_session, enrollment2)
    sit(db_session, enrollment2)
    assert (
        enrollment2.completion.certificate_snapshot["national_registry_id"]
        == "112233"
    )


def test_passed_result_payload_carries_the_completion(client, db_session):
    complete_profile(db_session)
    _, package, enrollment = setup_enrolled(client, db_session)
    answer_all_reviews(db_session, enrollment)
    start = client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment/attempts"
    )
    attempt_id = start.json()["attempt_id"]
    info = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment"
    ).json()
    answers = {
        str(q["question_id"]): q["choices"][0]["choice_id"]
        for q in info["questions"]
    }
    body = client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment/attempts"
        f"/{attempt_id}/submit",
        json={"answers": answers},
    ).json()
    assert body["status"] == "passed"
    assert body["completion"]["credit_awarded"] == "0.4"
    assert body["completion"]["certificate_ready"] is True
    assert body["completion"]["certificate_number"].endswith("-000001")

    [card] = client.get("/api/v1/my/courses").json()
    assert card["status"] == "completed"
    assert card["completion"]["certificate_number"] == (
        body["completion"]["certificate_number"]
    )
