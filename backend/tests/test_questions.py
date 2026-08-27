"""Feature 006: questions normalized from packages, video.blocks contract
rules, and the 5.01.2.1 review minimums."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.constants.question_minimums import required_review_questions
from app.models.question import Choice, Question
from tests.factories.package import OMIT, build_package
from tests.test_courses import ingest, upload


def make_question(i, kind, choices=4, after_block=1):
    question = {
        "id": f"q-{kind}-{i}",
        "kind": kind,
        "stem": f"Stem {kind} {i}?",
        "choices": [
            {"id": key, "text": f"Choice {key}"}
            for key in "abcdef"[:choices]
        ],
        "correct": "a",
        "feedback": f"Feedback for {kind} {i}.",
        "objective_ids": ["lo-1"],
    }
    if kind == "review":
        question["after_block"] = after_block
    return question


def questions_of(review=0, assessment=0, choices=4):
    return [
        make_question(i, "review", choices=choices) for i in range(review)
    ] + [make_question(i, "assessment", choices=choices) for i in range(assessment)]


def test_ingest_normalizes_questions_and_choices(
    client, admin_headers, db_session, tmp_path
):
    package_id = ingest(
        client,
        admin_headers,
        tmp_path,
        _questions=questions_of(review=5, assessment=3),
    )
    questions = list(
        db_session.scalars(
            select(Question)
            .where(Question.package_id == package_id)
            .order_by(Question.position)
        )
    )
    assert len(questions) == 8
    assert [q.kind for q in questions] == ["review"] * 5 + ["assessment"] * 3
    assert db_session.scalar(select(func.count()).select_from(Choice)) == 32
    for question in questions:
        assert sum(1 for c in question.choices if c.is_correct) == 1
        assert question.feedback
        if question.kind == "review":
            assert question.after_block is not None
        else:
            assert question.after_block is None


def test_version_two_gets_its_own_questions(
    client, admin_headers, db_session, tmp_path
):
    v1 = ingest(client, admin_headers, tmp_path)
    v2 = ingest(client, admin_headers, tmp_path, _transcript_marker="v2")
    assert v1 != v2
    v1_rows = db_session.scalars(
        select(Question).where(Question.package_id == v1)
    ).all()
    v2_rows = db_session.scalars(
        select(Question).where(Question.package_id == v2)
    ).all()
    assert len(v1_rows) == 2  # the factory default: 1 review + 1 assessment
    assert len(v2_rows) == 2
    assert {q.id for q in v1_rows}.isdisjoint({q.id for q in v2_rows})


def test_missing_blocks_refused(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path, manifest_overrides={"video": {"blocks": OMIT}}
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any(
        "manifest.video.blocks" in e and "missing" in e
        for e in response.json()["errors"]
    )


def test_non_contiguous_blocks_refused(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path,
        manifest_overrides={
            "video": {
                "blocks": [
                    {"id": "block-01", "start_seconds": 0.0, "end_seconds": 0.6},
                    {"id": "block-02", "start_seconds": 0.7, "end_seconds": 1.3},
                    {"id": "block-03", "start_seconds": 1.3, "end_seconds": 2.0},
                ]
            }
        },
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any("contiguous" in e for e in response.json()["errors"])


def test_blocks_ending_far_from_duration_refused(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path,
        manifest_overrides={
            "video": {
                "blocks": [
                    {"id": "block-01", "start_seconds": 0.0, "end_seconds": 0.3},
                    {"id": "block-02", "start_seconds": 0.3, "end_seconds": 0.6},
                    {"id": "block-03", "start_seconds": 0.6, "end_seconds": 0.9},
                ]
            }
        },
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any(
        "last end_seconds" in e and "1 second" in e
        for e in response.json()["errors"]
    )


def test_after_block_beyond_blocks_refused(client, admin_headers, tmp_path):
    questions = [make_question(1, "review", after_block=4)]
    response = upload(
        client, build_package(tmp_path, questions=questions), admin_headers
    )
    assert response.status_code == 422
    assert any(
        "after_block" in e and "[1, 3] (video.blocks)" in e
        for e in response.json()["errors"]
    )


@pytest.mark.parametrize(
    ("credit", "required"),
    [
        ("0.2", 0),
        ("0.4", 1),
        ("0.5", 2),
        ("0.6", 2),
        ("0.8", 3),
        ("1.0", 3),
        ("1.2", 3),
        ("1.4", 4),
        ("2.0", 6),
    ],
)
def test_required_review_questions(credit, required):
    assert required_review_questions(Decimal(credit)) == required


def test_required_review_questions_below_minimum_is_zero():
    assert required_review_questions(Decimal("0.0")) == 0
