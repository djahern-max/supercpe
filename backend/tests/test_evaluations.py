"""Feature 011: program evaluations (4.04, 4.04.1) and the 4.04.2 review
of results.

The load-bearing rules: solicited, never required (the prompt appears and
then stops, and nothing was withheld); one evaluation per completion; item
5 (instructors) is constrained to null because self study has none; and
"periodically review" is a reported 90-day warn finding, never enforced.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.constants.evaluation import (
    EVALUATION_REVIEW_DAYS,
    RATED_ELEMENTS,
    SOLICIT_UNTIL_DAYS,
)
from app.services import evaluations, readiness
from app.services.evaluations import EvaluationRuleViolation
from tests.conftest import login, make_account
from tests.test_completion import make_completed, sit
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    answer_all_reviews,
    enroll,
    make_participant,
)

GOOD_RATINGS = {
    "objectives_met": 5,
    "prerequisites_appropriate": 4,
    "materials_relevant": 5,
    "time_appropriate": 4,
}


def second_completion(db, course):
    """A second participant completes the same course."""
    other = make_participant(db, email="kim@supercpe.test", display_name="Kim")
    enrollment = enroll(db, course, other)
    answer_all_reviews(db, enrollment)
    attempt = sit(db, enrollment)
    assert attempt.status == "passed"
    return enrollment.completion


# --- solicitation -----------------------------------------------------------


def test_prompt_shown_after_completion_and_hidden_after_submit(
    client, db_session
):
    _, enrollment, _ = make_completed(db_session)
    completion = enrollment.completion
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)

    [card] = client.get("/api/v1/my/courses").json()
    assert card["completion"]["evaluation_requested"] is True

    info = client.get(
        f"/api/v1/my/completions/{completion.id}/evaluation"
    ).json()
    assert info["due"] is True
    assert info["submitted"] is False
    # Only the four applicable elements are asked; item 5 never is.
    assert [p["key"] for p in info["prompts"]] == list(RATED_ELEMENTS)

    submitted = client.post(
        f"/api/v1/my/completions/{completion.id}/evaluation",
        json={"ratings": GOOD_RATINGS, "comments": "Great course."},
    )
    assert submitted.status_code == 201, submitted.json()

    [card] = client.get("/api/v1/my/courses").json()
    assert card["completion"]["evaluation_requested"] is False
    info = client.get(
        f"/api/v1/my/completions/{completion.id}/evaluation"
    ).json()
    assert info["due"] is False
    assert info["submitted"] is True


def test_prompt_hidden_after_solicit_window(db_session):
    _, enrollment, _ = make_completed(db_session)
    completion = enrollment.completion
    assert evaluations.solicit(db_session, completion) is True
    completion.completed_at = datetime.now(timezone.utc) - timedelta(
        days=SOLICIT_UNTIL_DAYS + 1
    )
    db_session.commit()
    assert evaluations.solicit(db_session, completion) is False


def test_result_payload_carries_the_solicitation(db_session):
    from app.services import assessment as assessment_service

    _, enrollment, attempt = make_completed(db_session)
    result = assessment_service.result(attempt)
    assert result["completion"]["evaluation_requested"] is True


# --- submission rules -------------------------------------------------------


def test_ratings_outside_the_scale_refused(db_session):
    _, enrollment, _ = make_completed(db_session)
    with pytest.raises(EvaluationRuleViolation) as exc:
        evaluations.submit(
            db_session,
            enrollment.completion,
            GOOD_RATINGS | {"objectives_met": 6},
        )
    assert "between 1 and 5" in exc.value.errors[0]
    with pytest.raises(EvaluationRuleViolation):
        evaluations.submit(
            db_session,
            enrollment.completion,
            GOOD_RATINGS | {"time_appropriate": 0},
        )


def test_instructors_effective_cannot_be_set(db_session):
    _, enrollment, _ = make_completed(db_session)
    with pytest.raises(EvaluationRuleViolation) as exc:
        evaluations.submit(
            db_session,
            enrollment.completion,
            GOOD_RATINGS | {"instructors_effective": 5},
        )
    assert "not applicable" in exc.value.errors[0]

    # The recorded row visibly answers item 5 as null.
    row = evaluations.submit(db_session, enrollment.completion, GOOD_RATINGS)
    assert row.instructors_effective is None


def test_second_submission_refused(client, db_session):
    _, enrollment, _ = make_completed(db_session)
    evaluations.submit(db_session, enrollment.completion, GOOD_RATINGS)
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    refused = client.post(
        f"/api/v1/my/completions/{enrollment.completion.id}/evaluation",
        json={"ratings": GOOD_RATINGS},
    )
    assert refused.status_code == 422
    assert "already recorded" in refused.json()["errors"][0]


def test_missing_element_refused(db_session):
    _, enrollment, _ = make_completed(db_session)
    incomplete = dict(GOOD_RATINGS)
    del incomplete["materials_relevant"]
    with pytest.raises(EvaluationRuleViolation, match="materials_relevant"):
        evaluations.submit(db_session, enrollment.completion, incomplete)


def test_foreign_completion_is_404(client, db_session):
    _, enrollment, _ = make_completed(db_session)
    make_account(
        db_session, "other@supercpe.test", PARTICIPANT_PASSWORD, "participant"
    )
    login(client, "other@supercpe.test", PARTICIPANT_PASSWORD)
    response = client.get(
        f"/api/v1/my/completions/{enrollment.completion.id}/evaluation"
    )
    assert response.status_code == 404


def test_objectives_snapshot_copies_the_pinned_objectives(db_session):
    _, enrollment, _ = make_completed(db_session)
    row = evaluations.submit(db_session, enrollment.completion, GOOD_RATINGS)
    [lesson] = row.objectives_snapshot
    assert lesson["lesson_id"] == "GOLD-01"
    assert lesson["version"] == 1
    assert lesson["objectives"] == [{"id": "lo-1", "text": "Objective lo-1"}]


# --- summary ----------------------------------------------------------------


def test_summary_means_are_decimal_and_comments_ordered(db_session):
    course, enrollment, _ = make_completed(db_session)
    evaluations.submit(
        db_session, enrollment.completion, GOOD_RATINGS, comments="First."
    )
    other = second_completion(db_session, course)
    evaluations.submit(
        db_session,
        other,
        {k: 4 for k in RATED_ELEMENTS},
        comments="Second.",
    )

    summary = evaluations.summary(db_session, course)
    assert summary["n"] == 2
    # (5 + 4) / 2 computed with Decimal, serialized as a string.
    assert summary["elements"]["objectives_met"]["mean"] == str(Decimal("4.50"))
    assert summary["elements"]["time_appropriate"]["mean"] == "4.00"
    assert summary["elements"]["objectives_met"]["distribution"] == {
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 1,
        "5": 1,
    }
    assert summary["instructors_effective"] == "not applicable (self study)"
    assert [c["comments"] for c in summary["comments"]] == ["First.", "Second."]


def test_admin_summary_names_the_developer(client, admin_headers, db_session):
    course, enrollment, _ = make_completed(db_session)
    evaluations.submit(db_session, enrollment.completion, GOOD_RATINGS)
    body = client.get(
        f"/api/v1/admin/courses/{course.course_code}/evaluations",
        headers=admin_headers,
    ).json()
    # 4.04.2 "should inform developers": no email exists until 018, so the
    # page names the developer of record beside the results.
    assert body["developer_name"] == "Dev CPA"
    assert body["summary"]["n"] == 1
    [row] = body["rows"]
    assert row["objectives_met"] == 5
    assert row["instructors_effective"] is None


# --- the 4.04.2 review and its due finding ----------------------------------


def test_evaluation_review_due_fires_and_clears(
    client, admin_headers, db_session, admin_account
):
    course, enrollment, _ = make_completed(db_session)
    row = evaluations.submit(db_session, enrollment.completion, GOOD_RATINGS)

    codes = [f.code for f in readiness.check(db_session, course)]
    assert "evaluation_review_due" not in codes

    row.submitted_at = datetime.now(timezone.utc) - timedelta(
        days=EVALUATION_REVIEW_DAYS + 1
    )
    db_session.commit()
    [finding] = [
        f
        for f in readiness.check(db_session, course)
        if f.code == "evaluation_review_due"
    ]
    assert finding.level == "warn"
    assert course.course_code in finding.message

    # The sponsor panel reports it among the launch findings, as a warn —
    # it never blocks opening the site.
    body = client.get("/api/v1/admin/sponsor", headers=admin_headers).json()
    due = [
        f
        for f in body["launch_findings"]
        if f["code"] == "evaluation_review_due"
    ]
    assert len(due) == 1 and due[0]["level"] == "warn"

    recorded = client.post(
        f"/api/v1/admin/courses/{course.course_code}/evaluation-reviews",
        json={"note": "Looked fine.", "informed_developer": True},
        headers=admin_headers,
    )
    assert recorded.status_code == 201, recorded.json()
    assert recorded.json()["informed_developer"] is True
    assert recorded.json()["summary_snapshot"]["n"] == 1

    codes = [f.code for f in readiness.check(db_session, course)]
    assert "evaluation_review_due" not in codes

    history = client.get(
        f"/api/v1/admin/courses/{course.course_code}/evaluation-reviews",
        headers=admin_headers,
    ).json()
    assert len(history) == 1


def test_review_snapshot_is_as_of_its_date(db_session, admin_account):
    course, enrollment, _ = make_completed(db_session)
    evaluations.submit(db_session, enrollment.completion, GOOD_RATINGS)
    review = evaluations.record_review(db_session, course, admin_account)
    assert review.summary_snapshot["n"] == 1

    other = second_completion(db_session, course)
    evaluations.submit(db_session, other, GOOD_RATINGS)
    # The recorded snapshot does not move with later evaluations.
    db_session.refresh(review)
    assert review.summary_snapshot["n"] == 1
    assert evaluations.summary(db_session, course)["n"] == 2
