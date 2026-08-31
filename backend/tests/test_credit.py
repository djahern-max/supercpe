"""Feature 005: Method 2 credit measurement (7.02.6, 7.02.7).

The unit-level tests build course and package rows directly in the database,
because ingest verifies manifest durations against the real file with
ffprobe and the interesting durations (486 s) would need real 486-second
videos. The API-level tests go through the real ingest with the 2-second
factory package.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from app.models.course import Course, CourseLesson
from app.models.lesson_package import LessonPackage
from app.services import credit
from tests.test_courses import (
    COURSES_URL,
    PUBLIC_URL,
    attach,
    get_detail,
    ingest,
    make_course,
)


def make_question(i, kind):
    question = {
        "id": f"q-{kind}-{i}",
        "kind": kind,
        "stem": "Stem?",
        "choices": [
            {"id": "a", "text": "A"},
            {"id": "b", "text": "B"},
            {"id": "c", "text": "C"},
        ],
        "correct": "a",
        "feedback": "Because.",
        "objective_ids": ["lo-1"],
    }
    if kind == "review":
        question["after_block"] = 1
    return question


def questions_of(review=0, assessment=0):
    return [make_question(i, "review") for i in range(review)] + [
        make_question(i, "assessment") for i in range(assessment)
    ]


def make_package_row(
    db,
    lesson_id="GOLD-01",
    version=1,
    duration_seconds=486,
    av_is_additional_learning=True,
    word_count=0,
    questions=None,
    objectives=("lo-1",),
):
    package = LessonPackage(
        lesson_id=lesson_id,
        version=version,
        content_hash=f"hash-{lesson_id}-v{version}",
        title=f"Lesson {lesson_id}",
        duration_seconds=duration_seconds,
        duration_source="measured",
        measured_at=datetime.now(timezone.utc),
        narration_blocks=1,
        word_count=word_count,
        av_is_additional_learning=av_is_additional_learning,
        field_of_study="Accounting",
        knowledge_level="Basic",
        prerequisites="None",
        advance_preparation="None",
        manifest={
            "course_code": "GOLD",
            "position": 1,
            "learning_objectives": [
                {"id": key, "text": f"Objective {key}"} for key in objectives
            ],
        },
        questions=questions if questions is not None else [],
        transcript="transcript",
        video_key=f"packages/{lesson_id}/v{version}/video.mp4",
    )
    db.add(package)
    db.commit()
    return package


def make_course_row(db, course_code="GOLD", *packages):
    # 018: publish requires a price (business rule); the factory sets one
    # so only the price tests exercise its absence.
    course = Course(
        course_code=course_code,
        title=f"Course {course_code}",
        price_cents=4900,
    )
    for position, package in enumerate(packages, start=1):
        course.lessons.append(
            CourseLesson(package_id=package.id, position=position)
        )
    db.add(course)
    db.commit()
    return course


def test_golden_case_all_video_486s_8_questions(db_session):
    """7.02.7's own shape: no words, actual video time plus questions.
    486 s -> 8.10 min, 8 x 1.85 -> 14.80 min, 22.90 / 50 = 0.458, award 0.4
    (the number abacadaba's session notes recorded)."""
    package = make_package_row(
        db_session, questions=questions_of(review=6, assessment=2)
    )
    course = make_course_row(db_session, "GOLD", package)

    breakdown = credit.compute(db_session, course.id)
    assert breakdown.word_count == 0
    assert breakdown.av_seconds == 486
    assert breakdown.question_count == 8
    assert breakdown.word_minutes == Decimal("0.00")
    assert breakdown.av_minutes == Decimal("8.10")
    assert breakdown.question_minutes == Decimal("14.80")
    assert breakdown.raw_minutes == Decimal("22.90")
    assert breakdown.raw_credit == Decimal("0.458")
    assert breakdown.award == Decimal("0.4")
    assert breakdown.formula_version == "2026-7.02.6"


def test_narration_lesson_contributes_words_not_duration(db_session):
    package = make_package_row(
        db_session,
        duration_seconds=300,
        av_is_additional_learning=False,
        word_count=900,
    )
    course = make_course_row(db_session, "GOLD", package)

    breakdown = credit.compute(db_session, course.id)
    [row] = breakdown.rows
    assert row.av_seconds_counted == 0
    assert row.words_counted == 900
    assert breakdown.av_seconds == 0
    assert breakdown.word_count == 900
    # 900 words / 180 words per minute
    assert breakdown.word_minutes == Decimal("5.00")
    assert breakdown.av_minutes == Decimal("0.00")


def test_review_and_assessment_questions_both_count(db_session):
    package = make_package_row(
        db_session, questions=questions_of(review=5, assessment=3)
    )
    course = make_course_row(db_session, "GOLD", package)

    breakdown = credit.compute(db_session, course.id)
    [row] = breakdown.rows
    assert row.review_questions == 5
    assert row.assessment_questions == 3
    assert breakdown.question_count == 8


def test_two_lessons_sum_and_breakdown_is_in_position_order(db_session):
    first = make_package_row(
        db_session, lesson_id="GOLD-01", questions=questions_of(review=2)
    )
    second = make_package_row(
        db_session,
        lesson_id="GOLD-02",
        duration_seconds=0,
        av_is_additional_learning=False,
        word_count=900,
        questions=questions_of(assessment=1),
    )
    course = make_course_row(db_session, "GOLD", first, second)

    breakdown = credit.compute(db_session, course.id)
    assert [row.lesson_id for row in breakdown.rows] == ["GOLD-01", "GOLD-02"]
    assert [row.position for row in breakdown.rows] == [1, 2]
    assert breakdown.av_seconds == 486
    assert breakdown.word_count == 900
    assert breakdown.question_count == 3
    # 8.10 + 5.00 + 5.55
    assert breakdown.raw_minutes == Decimal("18.65")


def test_round_down_never_up():
    assert credit.round_down(Decimal("0.19")) == Decimal("0.0")
    assert credit.round_down(Decimal("0.20")) == Decimal("0.2")
    assert credit.round_down(Decimal("0.99")) == Decimal("0.8")
    assert credit.round_down(Decimal("1.0")) == Decimal("1.0")


def test_attach_recomputes_and_clears_staleness_detach_recomputes(
    client, admin_headers, db_session, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    # Force the never-computed state so attach demonstrably clears it.
    db_session.execute(
        text("UPDATE courses SET credit_computed_at = NULL")
    )
    db_session.commit()
    detail = get_detail(client, admin_headers, "ASC606-CON")
    assert detail["credit"]["is_stale"] is True
    assert detail["credit"]["stale_reason"] == "credit has never been computed"

    response = attach(client, admin_headers, "ASC606-CON", package_id)
    assert response.status_code == 200
    panel = response.json()["credit"]
    assert panel["is_stale"] is False
    assert panel["stale_reason"] is None
    # Factory package: 2 s of video, 1 review + 1 assessment question.
    assert panel["av_seconds"] == 2
    assert panel["question_count"] == 2
    assert panel["question_minutes"] == "3.70"
    assert panel["raw_minutes"] == "3.73"
    assert panel["award"] == "0.0"
    [row] = panel["rows"]
    assert row["review_questions"] == 1
    assert row["assessment_questions"] == 1

    detached = client.delete(
        f"{COURSES_URL}/ASC606-CON/lessons/{package_id}", headers=admin_headers
    )
    assert detached.status_code == 200
    panel = detached.json()["credit"]
    assert panel["is_stale"] is False
    assert panel["rows"] == []
    assert panel["award"] == "0.0"
    assert panel["question_count"] == 0


def test_formula_version_change_makes_stored_credit_stale(
    db_session, monkeypatch
):
    package = make_package_row(db_session, questions=questions_of(review=6))
    course = make_course_row(db_session, "GOLD", package)
    credit.store(db_session, course.id)
    db_session.refresh(course)
    assert credit.is_stale(course) is False

    monkeypatch.setattr(credit, "CREDIT_FORMULA_VERSION", "2030-x")
    assert credit.is_stale(course) is True
    assert "formula version changed" in credit.stale_reason(course)


def test_recompute_endpoint_refreshes_a_stale_credit(
    client, admin_headers, db_session, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200
    db_session.execute(text("UPDATE courses SET credit_computed_at = NULL"))
    db_session.commit()
    assert get_detail(client, admin_headers, "ASC606-CON")["credit"]["is_stale"]

    response = client.post(
        f"{COURSES_URL}/ASC606-CON/credit/recompute", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["credit"]["is_stale"] is False


def test_public_payload_serves_credit_when_fresh_and_refuses_when_stale(
    client, admin_headers, db_session, tmp_path
):
    # Six questions push the factory package over the minimum awardable:
    # 0.03 + 6 x 1.85 = 11.13 minutes -> 0.222 raw -> 0.2 awarded.
    package_id = ingest(
        client,
        admin_headers,
        tmp_path,
        _questions=questions_of(review=4, assessment=2),
    )
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200

    course = db_session.query(Course).one()
    course.status = "published"
    db_session.commit()

    detail = client.get(f"{PUBLIC_URL}/ASC606-CON").json()
    assert detail["recommended_credit"] == "0.2"
    assert detail["credit_basis"] == "Word count formula, 2026 Standards 7.02.6"
    [summary] = client.get(PUBLIC_URL).json()
    assert summary["recommended_credit"] == "0.2"

    # 016: a stale credit no longer serves null — the payload refuses to
    # render the course at all (a page missing item 3 would be partial
    # disclosure), and the catalog omits it.
    db_session.execute(text("UPDATE courses SET credit_computed_at = NULL"))
    db_session.commit()
    assert client.get(f"{PUBLIC_URL}/ASC606-CON").status_code == 404
    assert client.get(PUBLIC_URL).json() == []


def test_public_payload_never_serves_a_zero_award(
    client, admin_headers, db_session, tmp_path
):
    # The plain factory package awards 0.0 (3.73 minutes); the row is
    # served as null, never as "0.0".
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200
    course = db_session.query(Course).one()
    course.status = "published"
    db_session.commit()

    detail = client.get(f"{PUBLIC_URL}/ASC606-CON").json()
    assert detail["recommended_credit"] is None
    assert detail["credit_basis"] is None


def test_as_text_reproduces_the_award_by_hand(db_session):
    package = make_package_row(
        db_session, questions=questions_of(review=6, assessment=2)
    )
    course = make_course_row(db_session, "GOLD", package)
    breakdown = credit.store(db_session, course.id)
    rendered = credit.as_text(breakdown)

    # The numbers a reviewer would read off the record...
    assert "0 / 180 = 0.00 minutes" in rendered
    assert "486 s / 60 = 8.10 minutes" in rendered
    assert "8 x 1.85 = 14.80 minutes" in rendered
    assert "0.00 + 8.10 + 14.80 = 22.90 minutes" in rendered
    assert "22.90 / 50 = 0.458 raw credit" in rendered
    assert "Recommended CPE credit: 0.4" in rendered

    # ...re-added by hand, reproduce the stored award.
    by_hand = Decimal("0.00") + Decimal("8.10") + Decimal("14.80")
    assert by_hand == Decimal("22.90")
    assert credit.round_down(by_hand / Decimal(50)) == breakdown.award

    # And the stored breakdown alone rebuilds the same record (9.02.2(2)(ii)).
    db_session.refresh(course)
    assert credit.as_text(credit.from_stored(course)) == rendered
