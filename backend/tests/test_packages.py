from sqlalchemy import func, select

from app.models.lesson_package import LessonPackage
from tests.factories.package import DEFAULT_LESSON_ID, build_package

UPLOAD_URL = "/api/v1/admin/packages"


def upload(client, zip_path, headers):
    with open(zip_path, "rb") as f:
        return client.post(
            UPLOAD_URL,
            files={"file": ("package.zip", f, "application/zip")},
            headers=headers,
        )


def row_count(db_session):
    return db_session.scalar(select(func.count()).select_from(LessonPackage))


def test_valid_package_ingests(client, admin_headers, storage_root, tmp_path):
    response = upload(client, build_package(tmp_path), admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    package = body["package"]
    assert package["lesson_id"] == DEFAULT_LESSON_ID
    assert package["version"] == 1
    assert package["duration_source"] == "measured"
    expected_key = f"packages/{DEFAULT_LESSON_ID}/v1/video.mp4"
    assert package["video_key"] == expected_key
    assert (storage_root / expected_key).is_file()


def test_no_session_401(client, tmp_path):
    response = upload(client, build_package(tmp_path), {})
    assert response.status_code == 401


def test_bogus_session_cookie_401(client, tmp_path):
    response = upload(
        client,
        build_package(tmp_path),
        {"Cookie": "supercpe_session=not-a-real-token"},
    )
    assert response.status_code == 401


def test_estimated_duration_refused(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path, manifest_overrides={"video": {"duration_source": "estimated"}}
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any("7.02.7" in e and "duration_source" in e for e in errors)


def test_duration_mismatch_shows_both_numbers(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path, manifest_overrides={"video": {"duration_seconds": 4}}
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    # Rule 18 also flags the blocks now ending far from the declared
    # duration; this test is about the ffprobe comparison.
    [error] = [e for e in response.json()["errors"] if "ffprobe" in e]
    assert "4" in error
    assert "2." in error  # ffprobe's measured reading of the 2-second fixture


def test_tampered_transcript_refused(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path, tamper_transcript="# Block 1\n\nEdited after export.\n"
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any("content_hash" in e for e in response.json()["errors"])


def test_three_broken_fields_return_three_messages(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path,
        manifest_overrides={
            "field_of_study": "Astrology",
            "knowledge_level": "Wizard",
            "word_count": -5,
        },
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert len(errors) == 3
    assert any("field_of_study" in e for e in errors)
    assert any("knowledge_level" in e for e in errors)
    assert any("word_count" in e for e in errors)


def test_identical_reupload_is_idempotent(client, admin_headers, db_session, tmp_path):
    zip_path = build_package(tmp_path)
    first = upload(client, zip_path, admin_headers)
    assert first.status_code == 201
    second = upload(client, zip_path, admin_headers)
    assert second.status_code == 200
    body = second.json()
    assert body["created"] is False
    assert body["package"]["id"] == first.json()["package"]["id"]
    assert row_count(db_session) == 1


def test_changed_transcript_creates_version_two(client, admin_headers, tmp_path):
    first = upload(client, build_package(tmp_path), admin_headers)
    assert first.status_code == 201

    changed = build_package(
        tmp_path,
        transcript=(
            "## block-01\n\nRevised narration of record.\n\n"
            "## block-02\n\nSecond block.\n\n"
            "## block-03\n\nThird block.\n"
        ),
    )
    second = upload(client, changed, admin_headers)
    assert second.status_code == 201
    package = second.json()["package"]
    assert package["lesson_id"] == DEFAULT_LESSON_ID
    assert package["version"] == 2


def test_intermediate_blank_prerequisites_refused(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path,
        manifest_overrides={"knowledge_level": "Intermediate", "prerequisites": "  "},
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any(
        "prerequisites" in e and "3.02.1" in e for e in response.json()["errors"]
    )


def test_basic_blank_prerequisites_stored_as_none(client, admin_headers, tmp_path):
    zip_path = build_package(
        tmp_path,
        manifest_overrides={
            "knowledge_level": "Basic",
            "prerequisites": "",
            "advance_preparation": "",
        },
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 201
    package = response.json()["package"]
    assert package["prerequisites"] == "None"
    assert package["advance_preparation"] == "None"


def test_assessment_question_with_two_choices_refused(client, admin_headers, tmp_path):
    questions = [
        {
            "id": "q-01",
            "kind": "assessment",
            "stem": "A forced choice?",
            "choices": [
                {"id": "a", "text": "Yes"},
                {"id": "b", "text": "No"},
            ],
            "correct": "a",
            "feedback": "Assessment questions need at least three choices.",
            "objective_ids": ["lo-1"],
        }
    ]
    response = upload(
        client, build_package(tmp_path, questions=questions), admin_headers
    )
    assert response.status_code == 422
    assert any(
        "q-01" in e and "3 choices" in e for e in response.json()["errors"]
    )


def test_unknown_objective_id_refused(client, admin_headers, tmp_path):
    questions = [
        {
            "id": "q-01",
            "kind": "review",
            "after_block": 1,
            "stem": "Stem",
            "choices": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "correct": "a",
            "feedback": "Feedback.",
            "objective_ids": ["lo-99"],
        }
    ]
    response = upload(
        client, build_package(tmp_path, questions=questions), admin_headers
    )
    assert response.status_code == 422
    assert any("lo-99" in e for e in response.json()["errors"])


def test_after_block_beyond_narration_blocks_refused(client, admin_headers, tmp_path):
    questions = [
        {
            "id": "q-01",
            "kind": "review",
            "after_block": 7,  # fixture manifest has narration_blocks = 3
            "stem": "Stem",
            "choices": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "correct": "a",
            "feedback": "Feedback.",
            "objective_ids": ["lo-1"],
        }
    ]
    response = upload(
        client, build_package(tmp_path, questions=questions), admin_headers
    )
    assert response.status_code == 422
    assert any("after_block" in e and "7" in e for e in response.json()["errors"])


def test_unknown_field_of_study_refused(client, admin_headers, tmp_path):
    zip_path = build_package(tmp_path, manifest_overrides={"field_of_study": "Astrology"})
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any(
        "field_of_study" in e and "Astrology" in e for e in response.json()["errors"]
    )


def test_validation_failure_writes_nothing(
    client, admin_headers, db_session, storage_root, tmp_path
):
    zip_path = build_package(
        tmp_path, manifest_overrides={"video": {"duration_source": "estimated"}}
    )
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert row_count(db_session) == 0
    assert list(storage_root.rglob("*")) == []
