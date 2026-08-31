"""Feature 010: enrollment as the record everything hangs off.

The one-year expiration (9.02.2(3)) is stamped at creation; the pinned
package versions are what an in-flight participant keeps being served
whatever happens to the course; the player behind an enrollment persists
what 006 deliberately did not.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.account import Account
from app.models.enrollment import ReviewAnswer
from app.models.sme import SubjectMatterExpert
from app.services import credit, development, enrollments, questions
from app.services import courses as courses_service
from app.services.courses import DERIVED_FIELDS
from app.services.enrollments import EnrollmentRuleViolation
from tests.conftest import ADMIN_EMAIL, login, make_account
from tests.test_assessment import make_ready_course
from tests.test_credit import make_course_row, make_package_row
from tests.test_questions import questions_of

PARTICIPANT_EMAIL = "pat@supercpe.test"
PARTICIPANT_PASSWORD = "correct-horse-battery"


def make_sme(db, name, credential_type="cpa"):
    sme = SubjectMatterExpert(
        name=name,
        credentials="CPA",
        credential_type=credential_type,
        license_jurisdiction="NH",
        license_number="12345",
        license_status="active",
    )
    db.add(sme)
    db.commit()
    return sme


def make_recorder(db):
    existing = (
        db.query(Account).filter_by(email="recorder@supercpe.test").first()
    )
    if existing is not None:
        return existing
    account = Account(
        email="recorder@supercpe.test", password_hash="x", role="admin"
    )
    db.add(account)
    db.commit()
    return account


def make_publish_ready_course(db, course_code="GOLD"):
    """A course that clears every course-level publish gate: fresh
    credit, question minimums, description, developer, and an approved
    review by a second active CPA. Like test_assessment's
    make_ready_course, but with a distinct lesson per course code so
    several courses can coexist. What it deliberately does NOT do is
    publish the 8.01 item 8-10 policies, so 016's disclosure tests can
    prove the refusal."""
    package = make_package_row(
        db,
        lesson_id=f"{course_code}-01",
        duration_seconds=900,
        questions=questions_of(review=2, assessment=4),
    )
    questions.normalize(db, package)
    db.commit()
    course = make_course_row(db, course_code, package)
    credit.store(db, course.id)
    db.refresh(course)
    for field in DERIVED_FIELDS:
        setattr(course, field, getattr(package, field))
    course.description = "A course about gold."
    db.commit()
    developer = make_sme(db, "Dev CPA")
    reviewer = make_sme(db, "Rev CPA")
    development.set_developer(db, course, developer.id, True)
    development.record_review(
        db,
        course,
        reviewer.id,
        date.today(),
        "approved",
        recorded_by=make_recorder(db),
    )
    return course, package


def make_published_course(db, course_code="GOLD"):
    """A published course with the three policies published too — since
    016 the publish gate refuses without them (8.01 items 8-10)."""
    from tests.conftest import publish_test_policies

    course, package = make_publish_ready_course(db, course_code)
    publish_test_policies(db, make_recorder(db))
    courses_service.publish(db, course)
    return course, package


def make_participant(db, email=PARTICIPANT_EMAIL, display_name="Pat Smith"):
    from app.services import auth as auth_service

    return auth_service.create_account(
        db,
        email,
        "participant",
        PARTICIPANT_PASSWORD,
        created_by=None,
        display_name=display_name,
        must_change_password=False,
    )


def enroll(db, course, account):
    return enrollments.enroll(db, account, course, created_by=None)


def answer_all_reviews(db, enrollment, correct=True):
    """Answer every pinned review question; the factory's correct choice is
    always 'a'."""
    for _package, question_rows in enrollments.review_questions_for(
        db, enrollment
    ):
        for question in question_rows:
            choice = next(
                c for c in question.choices if c.is_correct == correct
            )
            enrollments.record_review_answer(db, enrollment, question, choice)


# --- enroll -----------------------------------------------------------------


def test_expires_exactly_one_year_after_enrollment(db_session):
    course, package = make_published_course(db_session)
    participant = make_participant(db_session)
    enrollment = enroll(db_session, course, participant)
    assert enrollment.expires_at - enrollment.enrolled_at == timedelta(days=365)
    assert enrollment.package_versions == {str(package.id): 1}
    assert enrollment.source == "admin"
    assert enrollments.status(enrollment) == "active"


def test_second_active_enrollment_refused_naming_the_first(db_session):
    course, _ = make_published_course(db_session)
    participant = make_participant(db_session)
    first = enroll(db_session, course, participant)
    with pytest.raises(EnrollmentRuleViolation) as exc:
        enroll(db_session, course, participant)
    assert str(first.id) in exc.value.errors[0]

    # An expired enrollment no longer blocks a new one.
    first.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    assert enrollments.status(first) == "expired"
    second = enroll(db_session, course, participant)
    assert second.id != first.id


def test_enrolling_on_a_draft_course_refused(db_session):
    course, _ = make_ready_course(db_session)
    participant = make_participant(db_session)
    with pytest.raises(EnrollmentRuleViolation, match="draft"):
        enroll(db_session, course, participant)


def test_enrolling_a_reviewer_refused(db_session):
    course, _ = make_published_course(db_session)
    reviewer = make_account(
        db_session, "rev@supercpe.test", PARTICIPANT_PASSWORD, "reviewer"
    )
    with pytest.raises(EnrollmentRuleViolation, match="reviewer"):
        enroll(db_session, course, reviewer)


# --- pinning ----------------------------------------------------------------


def update_to_v2_and_republish(db_session, course, package):
    """The full correction cycle 008 requires: unpublish, swap the version,
    re-review, republish."""
    courses_service.unpublish(db_session, course)
    v2 = make_package_row(
        db_session,
        version=2,
        duration_seconds=900,
        questions=questions_of(review=2, assessment=4),
    )
    questions.normalize(db_session, v2)
    db_session.commit()
    courses_service.update_version(db_session, course, package.id, v2.id)
    reviewer = make_sme(db_session, "Second Rev CPA")
    recorder = db_session.query(Account).filter_by(role="admin").first()
    development.record_review(
        db_session,
        course,
        reviewer.id,
        date.today(),
        "approved",
        recorded_by=recorder,
    )
    courses_service.publish(db_session, course)
    return v2


def test_enrollment_keeps_the_pinned_version_through_an_update(db_session):
    course, package = make_published_course(db_session)
    participant = make_participant(db_session)
    enrollment = enroll(db_session, course, participant)

    v2 = update_to_v2_and_republish(db_session, course, package)

    # The in-flight enrollment still serves v1...
    [pinned] = enrollments.packages_for(db_session, enrollment)
    assert pinned.id == package.id
    assert pinned.version == 1
    assert enrollments.pinned_package(db_session, enrollment, v2.id) is None

    # ...and a new enrollment pins v2.
    other = make_participant(db_session, "pat2@supercpe.test")
    new_enrollment = enroll(db_session, course, other)
    assert new_enrollment.package_versions == {str(v2.id): 2}
    [new_pinned] = enrollments.packages_for(db_session, new_enrollment)
    assert new_pinned.id == v2.id


# --- the enrollment player --------------------------------------------------


def participant_client(client, db_session):
    make_participant(db_session)
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)


def play_url(enrollment_id, package_id):
    return f"/api/v1/my/enrollments/{enrollment_id}/lessons/{package_id}/play"


def review_url(enrollment_id, package_id, question_key):
    return (
        f"/api/v1/my/enrollments/{enrollment_id}/lessons/{package_id}"
        f"/review/{question_key}"
    )


def progress_url(enrollment_id, package_id):
    return (
        f"/api/v1/my/enrollments/{enrollment_id}/lessons/{package_id}/progress"
    )


def setup_enrolled(client, db_session):
    course, package = make_published_course(db_session)
    participant_client(client, db_session)
    participant = (
        db_session.query(Account).filter_by(email=PARTICIPANT_EMAIL).one()
    )
    enrollment = enroll(db_session, course, participant)
    return course, package, enrollment


def test_review_grading_persists_and_reanswer_updates(client, db_session):
    _, package, enrollment = setup_enrolled(client, db_session)

    wrong = client.post(
        review_url(enrollment.id, package.id, "q-review-0"),
        json={"choice_key": "b"},
    )
    assert wrong.status_code == 200
    body = wrong.json()
    # Exactly what 006 returned (5.01.2.2 feedback always).
    assert body["correct"] is False
    assert body["correct_choice_key"] == "a"
    assert body["feedback"].strip()

    [row] = db_session.query(ReviewAnswer).all()
    assert row.enrollment_id == enrollment.id
    assert row.is_correct is False
    first_answered_at = row.answered_at

    right = client.post(
        review_url(enrollment.id, package.id, "q-review-0"),
        json={"choice_key": "a"},
    )
    assert right.json()["correct"] is True
    [row] = db_session.query(ReviewAnswer).all()
    assert row.is_correct is True
    assert row.answered_at >= first_answered_at


def test_foreign_enrollment_is_404_not_403(client, db_session):
    course, package, enrollment = setup_enrolled(client, db_session)
    make_account(
        db_session, "other@supercpe.test", PARTICIPANT_PASSWORD, "participant"
    )
    login(client, "other@supercpe.test", PARTICIPANT_PASSWORD)
    assert client.get(play_url(enrollment.id, package.id)).status_code == 404
    assert (
        client.get(f"/api/v1/my/enrollments/{enrollment.id}").status_code == 404
    )


def test_progress_is_monotonic(client, db_session):
    _, package, enrollment = setup_enrolled(client, db_session)
    url = progress_url(enrollment.id, package.id)
    assert client.put(url, json={"furthest_seconds": 50}).json()[
        "furthest_seconds"
    ] == 50
    # A lower report never lowers the stored point.
    assert client.put(url, json={"furthest_seconds": 30}).json()[
        "furthest_seconds"
    ] == 50
    assert client.put(url, json={"furthest_seconds": 80}).json()[
        "furthest_seconds"
    ] == 80
    play = client.get(play_url(enrollment.id, package.id)).json()
    assert play["furthest_seconds"] == 80


def test_my_courses_lists_the_enrollment(client, db_session):
    course, _, enrollment = setup_enrolled(client, db_session)
    [card] = client.get("/api/v1/my/courses").json()
    assert card["enrollment_id"] == enrollment.id
    assert card["course_code"] == course.course_code
    assert card["status"] == "active"
    assert card["review_total"] == 2
    assert card["review_answered"] == 0
    assert card["assessment_available"] is False
    assert card["completion"] is None


# --- admin ------------------------------------------------------------------


def test_admin_enrolls_by_email_and_lists(client, admin_headers, db_session):
    course, package = make_published_course(db_session)
    make_participant(db_session)
    response = client.post(
        f"/api/v1/admin/courses/{course.course_code}/enrollments",
        json={"email": PARTICIPANT_EMAIL},
        headers=admin_headers,
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["email"] == PARTICIPANT_EMAIL
    assert body["status"] == "active"
    assert body["package_versions"] == {str(package.id): 1}

    unknown = client.post(
        f"/api/v1/admin/courses/{course.course_code}/enrollments",
        json={"email": "nobody@supercpe.test"},
        headers=admin_headers,
    )
    assert unknown.status_code == 422
    assert any("No account" in e for e in unknown.json()["errors"])

    admin = client.post(
        f"/api/v1/admin/courses/{course.course_code}/enrollments",
        json={"email": ADMIN_EMAIL},
        headers=admin_headers,
    )
    assert admin.status_code == 422

    [row] = client.get(
        f"/api/v1/admin/courses/{course.course_code}/enrollments",
        headers=admin_headers,
    ).json()
    assert row["email"] == PARTICIPANT_EMAIL
    assert row["review_total"] == 2
    assert row["has_completion"] is False
