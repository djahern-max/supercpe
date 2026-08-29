"""Feature 007: the qualified assessment (6.01.2).

The load-bearing tests here are the payload walks: a failed attempt's
result must contain no per-question data of any kind (6.01.2 sub-ii, no
test bank), and an open attempt's questions payload no answers or
feedback. Write these first; the engine exists to make them pass.
"""

from decimal import Decimal

import pytest

from app.constants.assessment import RETAKES_ALLOWED
from app.constants.question_minimums import required_assessment_questions
from app.services import assessment, credit, questions, readiness
from app.services.assessment import AssessmentRuleViolation
from tests.test_credit import make_course_row, make_package_row
from tests.test_questions import make_question, questions_of
from tests.test_player import walk_asserting_no_answer_key


PREVIEW_HEADER = {"X-Preview-Id": "previewer-1"}


def assessment_url(course_code="GOLD"):
    return f"/api/v1/courses/{course_code}/assessment"


def make_ready_course(
    db,
    course_code="GOLD",
    duration_seconds=900,
    question_list=None,
    objectives=("lo-1",),
):
    """A course whose assessment satisfies every 6.01.2 finding by default:
    900 s + (2 review + 4 assessment) x 1.85 = 26.10 min -> 0.522 -> 0.4
    credit, which requires 1 review and 3 assessment questions — both
    exceeded."""
    if question_list is None:
        question_list = questions_of(review=2, assessment=4)
    package = make_package_row(
        db,
        duration_seconds=duration_seconds,
        questions=question_list,
        objectives=objectives,
    )
    questions.normalize(db, package)
    db.commit()
    course = make_course_row(db, course_code, package)
    credit.store(db, course.id)
    db.refresh(course)
    return course, package


def finding(findings, code):
    matches = [f for f in findings if f.code == code]
    return matches[0] if matches else None


def start_via_api(client, headers, course_code="GOLD"):
    response = client.post(
        f"{assessment_url(course_code)}/attempts", headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def answers_for(client, headers, wrong=0, course_code="GOLD"):
    """A complete answers map: the factory's first choice is always the
    correct one, so `wrong` questions get the second choice instead."""
    info = client.get(assessment_url(course_code), headers=headers).json()
    return {
        str(q["question_id"]): (
            q["choices"][1]["choice_id"]
            if i < wrong
            else q["choices"][0]["choice_id"]
        )
        for i, q in enumerate(info["questions"])
    }


# --- minimums ---------------------------------------------------------------


def test_required_assessment_questions_chart():
    chart = {"0.2": 2, "0.4": 3, "0.5": 4, "0.6": 4, "0.8": 5, "1.0": 5}
    for credit_str, required in chart.items():
        assert required_assessment_questions(Decimal(credit_str)) == required


def test_required_assessment_questions_worked_examples():
    # 6.01.2's own examples: 5 credits -> 25, 5 1/2 -> 29.
    assert required_assessment_questions(Decimal("5.0")) == 25
    assert required_assessment_questions(Decimal("5.5")) == 29
    assert required_assessment_questions(Decimal("1.2")) == 7


def test_assessment_minimum_finding_shows_both_numbers(db_session):
    # 1260 s + 5 x 1.85 = 30.25 min -> 0.605 -> 0.6 credit, which requires
    # 4 assessment questions; only 3 exist.
    course, _ = make_ready_course(
        db_session,
        duration_seconds=1260,
        question_list=questions_of(review=2, assessment=3),
    )
    found = finding(readiness.check(db_session, course), "assessment_minimum")
    assert found is not None
    assert found.level == "block"
    assert "3" in found.message and "4" in found.message


# --- duplicates -------------------------------------------------------------


def test_duplicate_stem_differing_case_and_punctuation(db_session):
    question_list = questions_of(review=2, assessment=3) + [
        make_question(9, "review", stem="Which measure depicts control?"),
        make_question(9, "assessment", stem="  which  measure DEPICTS control???"),
    ]
    course, _ = make_ready_course(db_session, question_list=question_list)
    found = finding(readiness.check(db_session, course), "assessment_duplicate")
    assert found is not None
    assert found.level == "block"
    assert "q-assessment-9" in found.message
    assert "q-review-9" in found.message
    assert "GOLD-01" in found.message


def test_stem_differing_by_one_word_is_not_duplicate(db_session):
    question_list = questions_of(review=2, assessment=3) + [
        make_question(9, "review", stem="Which measure depicts control?"),
        make_question(9, "assessment", stem="Which measure faithfully depicts control?"),
    ]
    course, _ = make_ready_course(db_session, question_list=question_list)
    assert finding(
        readiness.check(db_session, course), "assessment_duplicate"
    ) is None


# --- objective coverage -----------------------------------------------------


def coverage_course(db_session, covered_objectives):
    question_list = questions_of(review=2) + [
        make_question(i, "assessment", objective_ids=[key])
        for i, key in enumerate(covered_objectives)
    ] + [
        make_question(9, "assessment", objective_ids=[covered_objectives[0]])
    ]
    # Always 4 assessment questions so only coverage varies.
    question_list = question_list[: 2 + 4]
    course, _ = make_ready_course(
        db_session,
        question_list=question_list,
        objectives=("lo-1", "lo-2", "lo-3", "lo-4"),
    )
    return course


def test_three_of_four_objectives_is_75_pct_no_finding(db_session):
    course = coverage_course(db_session, ["lo-1", "lo-2", "lo-3"])
    assert finding(
        readiness.check(db_session, course), "objective_coverage"
    ) is None


def test_two_of_four_objectives_finding_lists_uncovered(db_session):
    course = coverage_course(db_session, ["lo-1", "lo-2", "lo-1"])
    found = finding(readiness.check(db_session, course), "objective_coverage")
    assert found is not None
    assert found.level == "block"
    assert "2 of 4" in found.message
    assert "lo-3" in found.message and "lo-4" in found.message
    assert "lo-1" not in found.message.split("Uncovered:")[1]


# --- start ------------------------------------------------------------------


def test_start_refuses_on_stale_credit(db_session):
    package = make_package_row(
        db_session, questions=questions_of(review=2, assessment=4)
    )
    questions.normalize(db_session, package)
    db_session.commit()
    course = make_course_row(db_session, "GOLD", package)
    # No credit.store: stale.
    with pytest.raises(AssessmentRuleViolation, match="stale"):
        assessment.start(db_session, course, "previewer-1")


def test_start_refuses_on_block_finding(db_session):
    course, _ = make_ready_course(
        db_session,
        duration_seconds=1260,
        question_list=questions_of(review=2, assessment=3),
    )
    with pytest.raises(AssessmentRuleViolation, match="not well-formed"):
        assessment.start(db_session, course, "previewer-1")


def test_start_records_package_versions(db_session):
    course, package = make_ready_course(db_session)
    attempt = assessment.start(db_session, course, "previewer-1")
    assert attempt.package_versions == [
        {"package_id": package.id, "version": 1}
    ]
    assert attempt.question_count == 4
    assert attempt.is_preview is True
    assert Decimal(attempt.passing_pct) == 70


def test_second_start_refused_abandon_then_start_works(db_session):
    course, _ = make_ready_course(db_session)
    first = assessment.start(db_session, course, "previewer-1")
    with pytest.raises(AssessmentRuleViolation, match="already open"):
        assessment.start(db_session, course, "previewer-1")
    # A different preview identity is not blocked by someone else's attempt.
    other = assessment.start(db_session, course, "previewer-2")
    assert other.id != first.id

    assessment.abandon(db_session, first)
    assert first.status == "failed"
    assert first.score_pct is None
    second = assessment.start(db_session, course, "previewer-1")
    assert second.id != first.id


# --- grading ----------------------------------------------------------------


def test_70_00_passes_69_99_fails():
    score, passed = assessment.grade(7, 10)
    assert (str(score), passed) == ("70.00", True)
    score, passed = assessment.grade(6999, 10000)
    assert (str(score), passed) == ("69.99", False)
    # 2 of 3 displays 66.67 but the exact ratio is what failed it.
    score, passed = assessment.grade(2, 3)
    assert (str(score), passed) == ("66.67", False)


def test_submit_refuses_with_unanswered_questions(client, admin_headers, db_session):
    headers = admin_headers | PREVIEW_HEADER
    make_ready_course(db_session)
    attempt = start_via_api(client, headers)
    answers = answers_for(client, headers)
    answers.pop(next(iter(answers)))
    response = client.post(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}/submit",
        json={"answers": answers},
        headers=headers,
    )
    assert response.status_code == 422
    assert any("unanswered" in e for e in response.json()["errors"])


# --- the sub-ii feedback rule ----------------------------------------------


FORBIDDEN_ON_FAIL = (
    "is_correct",
    "correct",
    "correct_choice_id",
    "correct_choice_key",
    "chosen_choice_id",
    "feedback",
    "questions",
    "answers",
)


def walk_asserting_no_feedback(node, path="$"):
    """6.01.2 sub-ii: on a failed assessment the sponsor may not provide
    feedback. No per-question data of any kind may appear, anywhere."""
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in FORBIDDEN_ON_FAIL, f"{key!r} at {path}"
            walk_asserting_no_feedback(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk_asserting_no_feedback(value, f"{path}[{i}]")


def test_failed_result_payload_has_no_feedback(client, admin_headers, db_session):
    headers = admin_headers | PREVIEW_HEADER
    make_ready_course(db_session)
    attempt = start_via_api(client, headers)
    response = client.post(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}/submit",
        json={"answers": answers_for(client, headers, wrong=2)},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["score_pct"] == "50.00"
    assert body["correct_count"] == 2
    assert body["question_count"] == 4
    assert body["retakes_allowed"] == RETAKES_ALLOWED
    walk_asserting_no_feedback(body)
    # The GET result is the same payload.
    fetched = client.get(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}", headers=headers
    ).json()
    walk_asserting_no_feedback(fetched)


def test_passed_result_payload_has_the_per_question_record(
    client, admin_headers, db_session
):
    headers = admin_headers | PREVIEW_HEADER
    make_ready_course(db_session)
    attempt = start_via_api(client, headers)
    response = client.post(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}/submit",
        json={"answers": answers_for(client, headers)},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["score_pct"] == "100.00"
    assert len(body["questions"]) == 4
    for question in body["questions"]:
        assert question["is_correct"] is True
        assert question["chosen_choice_id"] == question["correct_choice_id"]
        assert question["feedback"].strip()
        assert question["stem"]


def test_open_assessment_payload_has_no_answers_or_feedback(
    client, admin_headers, db_session
):
    headers = admin_headers | PREVIEW_HEADER
    make_ready_course(db_session)
    attempt = start_via_api(client, headers)
    info = client.get(assessment_url(), headers=headers).json()
    assert info["open_attempt_id"] == attempt["attempt_id"]
    assert info["question_count"] == 4
    walk_asserting_no_answer_key(info)
    assert "feedback" not in str(info)

    # Saved partial answers come back for a refresh, with no correctness.
    answers = answers_for(client, headers)
    first_question = next(iter(answers))
    save = client.put(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}/answers",
        json={"answers": {first_question: answers[first_question]}},
        headers=headers,
    )
    assert save.status_code == 200
    assert save.json()["answered"] == 1
    fetched = client.get(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}", headers=headers
    ).json()
    assert fetched["status"] == "open"
    assert fetched["answers"] == {first_question: answers[first_question]}
    walk_asserting_no_answer_key(fetched)


# --- retention --------------------------------------------------------------


def test_package_versions_survive_a_version_update(db_session):
    from app.services import courses as courses_service
    from app.services.courses import DERIVED_FIELDS

    course, package = make_ready_course(db_session)
    # make_course_row skips attach_package, so copy the derived fields the
    # way attach would have; update_version checks agreement against them.
    for field in DERIVED_FIELDS:
        setattr(course, field, getattr(package, field))
    db_session.commit()
    attempt = assessment.start(db_session, course, "previewer-1")
    recorded = list(attempt.package_versions)

    v2 = make_package_row(
        db_session,
        version=2,
        duration_seconds=900,
        questions=questions_of(review=2, assessment=4),
    )
    questions.normalize(db_session, v2)
    db_session.commit()
    courses_service.update_version(db_session, course, package.id, v2.id)
    db_session.refresh(attempt)
    assert attempt.package_versions == recorded
    assert attempt.package_versions[0]["version"] == 1


def test_admin_attempts_endpoint_shows_everything(
    client, admin_headers, db_session
):
    headers = admin_headers | PREVIEW_HEADER
    make_ready_course(db_session)
    attempt = start_via_api(client, headers)
    client.post(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}/submit",
        json={"answers": answers_for(client, headers, wrong=2)},
        headers=headers,
    )
    response = client.get(
        "/api/v1/admin/courses/GOLD/attempts", headers=admin_headers
    )
    assert response.status_code == 200
    [row] = response.json()
    assert row["status"] == "failed"
    assert row["score_pct"] == "50.00"
    assert row["is_preview"] is True
    assert row["preview_id"] == "previewer-1"
    assert len(row["answers"]) == 4
    # The admin sees exactly what the participant may not: which answers a
    # failed attempt got wrong.
    assert sorted(a["is_correct"] for a in row["answers"]) == [
        False,
        False,
        True,
        True,
    ]
    for answer in row["answers"]:
        assert answer["chosen_text"]
        assert answer["correct_choice_id"]


def test_attempt_of_another_preview_identity_is_404(
    client, admin_headers, db_session
):
    headers = admin_headers | PREVIEW_HEADER
    make_ready_course(db_session)
    attempt = start_via_api(client, headers)
    other = admin_headers | {"X-Preview-Id": "previewer-2"}
    response = client.get(
        f"{assessment_url()}/attempts/{attempt['attempt_id']}", headers=other
    )
    assert response.status_code == 404
