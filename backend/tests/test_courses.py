from datetime import datetime

from app.models.course import Course
from tests.factories.package import OMIT, build_package


def ts(value):
    return datetime.fromisoformat(value)

COURSES_URL = "/api/v1/admin/courses"
PACKAGES_URL = "/api/v1/admin/packages"
PUBLIC_URL = "/api/v1/courses"

DEFAULT_COURSE = {"course_code": "ASC606-CON", "title": "Revenue Under ASC 606"}


def upload(client, zip_path, headers):
    with open(zip_path, "rb") as f:
        return client.post(
            PACKAGES_URL,
            files={"file": ("package.zip", f, "application/zip")},
            headers=headers,
        )


def ingest(client, headers, tmp_path, **manifest_overrides):
    """Ingest a factory package and return its id. Each distinct lesson or
    version needs a distinct transcript because the content hash ignores the
    manifest. `_questions` replaces the factory's question list."""
    marker = manifest_overrides.get("lesson_id", "default")
    version_marker = manifest_overrides.pop("_transcript_marker", "")
    questions = manifest_overrides.pop("_questions", None)
    transcript = f"# Block 1\n\nNarration for {marker} {version_marker}.\n"
    zip_path = build_package(
        tmp_path,
        manifest_overrides=manifest_overrides,
        questions=questions,
        transcript=transcript,
    )
    response = upload(client, zip_path, headers)
    assert response.status_code == 201, response.json()
    return response.json()["package"]["id"]


def make_course(client, headers, **overrides):
    response = client.post(
        COURSES_URL, json={**DEFAULT_COURSE, **overrides}, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()


def attach(client, headers, course_code, package_id, position=None):
    body = {"package_id": package_id}
    if position is not None:
        body["position"] = position
    return client.post(
        f"{COURSES_URL}/{course_code}/lessons", json=body, headers=headers
    )


def get_detail(client, headers, course_code):
    response = client.get(f"{COURSES_URL}/{course_code}", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_create_course_and_duplicate_code_refused(client, admin_headers):
    course = make_course(client, admin_headers)
    assert course["course_code"] == "ASC606-CON"
    assert course["status"] == "draft"
    assert course["field_of_study"] is None
    assert course["lessons"] == []

    response = client.post(COURSES_URL, json=DEFAULT_COURSE, headers=admin_headers)
    assert response.status_code == 422
    assert any("already in use" in e for e in response.json()["errors"])


def test_attach_sets_derived_fields_from_first_package(
    client, admin_headers, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    response = attach(client, admin_headers, "ASC606-CON", package_id)
    assert response.status_code == 200, response.json()
    course = response.json()
    assert course["field_of_study"] == "Accounting"
    assert course["knowledge_level"] == "Intermediate"
    assert course["prerequisites"] == "Basic familiarity with ASC 606"
    assert course["advance_preparation"] == "None"
    [lesson] = course["lessons"]
    assert lesson["position"] == 1  # from the manifest
    [group] = course["objectives"]
    assert group["lesson_id"] == "ASC606-CON-01"
    assert len(group["objectives"]) == 2


def test_attach_with_differing_knowledge_level_refused(
    client, admin_headers, tmp_path
):
    first = ingest(client, admin_headers, tmp_path)
    second = ingest(
        client,
        admin_headers,
        tmp_path,
        lesson_id="ASC606-CON-02",
        position=2,
        knowledge_level="Advanced",
    )
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", first).status_code == 200

    response = attach(client, admin_headers, "ASC606-CON", second)
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "knowledge_level" in error
    assert "Intermediate" in error
    assert "Advanced" in error


def test_attach_with_different_manifest_course_code_refused(
    client, admin_headers, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers, course_code="ASC842-PCX", title="Leases")
    response = attach(client, admin_headers, "ASC842-PCX", package_id)
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "ASC606-CON" in error
    assert "ASC842-PCX" in error


def test_two_versions_of_one_lesson_cannot_both_be_attached(
    client, admin_headers, tmp_path
):
    v1 = ingest(client, admin_headers, tmp_path)
    v2 = ingest(client, admin_headers, tmp_path, _transcript_marker="v2")
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", v1).status_code == 200

    response = attach(client, admin_headers, "ASC606-CON", v2)
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "already attached as v1" in error


def test_position_collision_refused(client, admin_headers, tmp_path):
    first = ingest(client, admin_headers, tmp_path)
    second = ingest(
        client, admin_headers, tmp_path, lesson_id="ASC606-CON-02", position=1
    )
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", first).status_code == 200

    response = attach(client, admin_headers, "ASC606-CON", second)
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "position 1" in error
    assert "ASC606-CON-01" in error


def test_reorder_keeps_positions_dense_and_unique(client, admin_headers, tmp_path):
    ids = {}
    for lesson_id, position in (
        ("ASC606-CON-01", 1),
        ("ASC606-CON-02", 2),
        ("ASC606-CON-03", 5),  # sparse on purpose
    ):
        ids[lesson_id] = ingest(
            client, admin_headers, tmp_path, lesson_id=lesson_id, position=position
        )
    make_course(client, admin_headers)
    for lesson_id in ids:
        assert (
            attach(client, admin_headers, "ASC606-CON", ids[lesson_id]).status_code
            == 200
        )

    response = client.post(
        f"{COURSES_URL}/ASC606-CON/lessons/{ids['ASC606-CON-03']}/move",
        json={"direction": "up"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    lessons = response.json()["lessons"]
    assert [l["lesson_id"] for l in lessons] == [
        "ASC606-CON-01",
        "ASC606-CON-03",
        "ASC606-CON-02",
    ]
    assert [l["position"] for l in lessons] == [1, 2, 3]


def test_update_version_swaps_package_and_bumps_content_updated_at(
    client, admin_headers, tmp_path
):
    v1 = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", v1).status_code == 200
    before = get_detail(client, admin_headers, "ASC606-CON")
    [lesson] = before["lessons"]
    assert lesson["newer_version"] is None

    v2 = ingest(client, admin_headers, tmp_path, _transcript_marker="v2")
    [lesson] = get_detail(client, admin_headers, "ASC606-CON")["lessons"]
    assert lesson["newer_version"] == 2
    assert lesson["newer_package_id"] == v2

    response = client.post(
        f"{COURSES_URL}/ASC606-CON/lessons/{v1}/update-version",
        json={"new_package_id": v2},
        headers=admin_headers,
    )
    assert response.status_code == 200
    after = response.json()
    [lesson] = after["lessons"]
    assert lesson["package_id"] == v2
    assert lesson["version"] == 2
    assert lesson["position"] == 1
    assert ts(after["content_updated_at"]) > ts(before["content_updated_at"])


def test_detach_and_reorder_bump_content_updated_at_but_a_read_does_not(
    client, admin_headers, tmp_path
):
    first = ingest(client, admin_headers, tmp_path)
    second = ingest(
        client, admin_headers, tmp_path, lesson_id="ASC606-CON-02", position=2
    )
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", first).status_code == 200
    assert attach(client, admin_headers, "ASC606-CON", second).status_code == 200

    t0 = get_detail(client, admin_headers, "ASC606-CON")["content_updated_at"]
    assert get_detail(client, admin_headers, "ASC606-CON")["content_updated_at"] == t0

    moved = client.post(
        f"{COURSES_URL}/ASC606-CON/lessons/{second}/move",
        json={"direction": "up"},
        headers=admin_headers,
    )
    assert moved.status_code == 200
    t1 = moved.json()["content_updated_at"]
    assert ts(t1) > ts(t0)

    detached = client.delete(
        f"{COURSES_URL}/ASC606-CON/lessons/{second}", headers=admin_headers
    )
    assert detached.status_code == 200
    assert ts(detached.json()["content_updated_at"]) > ts(t1)


def test_delete_attached_package_refused_unattached_removes_storage(
    client, admin_headers, storage_root, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200

    response = client.delete(
        f"{PACKAGES_URL}/{package_id}", headers=admin_headers
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "attached" in error and "ASC606-CON" in error

    listed = client.get(PACKAGES_URL, headers=admin_headers).json()
    assert listed[0]["attached_to"] == "ASC606-CON"

    video_key = "packages/ASC606-CON-01/v1/video.mp4"
    assert (storage_root / video_key).is_file()
    detach = client.delete(
        f"{COURSES_URL}/ASC606-CON/lessons/{package_id}", headers=admin_headers
    )
    assert detach.status_code == 200
    deleted = client.delete(f"{PACKAGES_URL}/{package_id}", headers=admin_headers)
    assert deleted.status_code == 204
    assert not (storage_root / video_key).is_file()
    assert client.get(
        f"{PACKAGES_URL}/{package_id}", headers=admin_headers
    ).status_code == 404


def test_public_catalog_serves_only_published(
    client, admin_headers, db_session, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200

    # Everything is draft: the catalog is empty and the detail 404s.
    assert client.get(PUBLIC_URL).json() == []
    assert client.get(f"{PUBLIC_URL}/ASC606-CON").status_code == 404

    # Flipped to published (008 owns the real gate), the 8.01 payload appears.
    course = db_session.query(Course).one()
    course.status = "published"
    db_session.commit()

    [summary] = client.get(PUBLIC_URL).json()
    assert summary["course_code"] == "ASC606-CON"
    detail = client.get(f"{PUBLIC_URL}/ASC606-CON").json()
    assert detail["title"] == "Revenue Under ASC 606"
    assert detail["field_of_study"] == "Accounting"
    assert detail["knowledge_level"] == "Intermediate"
    assert detail["prerequisites"] == "Basic familiarity with ASC 606"
    assert detail["advance_preparation"] == "None"
    assert detail["objectives"][0]["lesson_id"] == "ASC606-CON-01"
    assert detail["lessons"][0]["duration_seconds"] == 2
    assert "package_id" not in detail["objectives"][0]


def test_manifest_without_course_code_refused_at_ingest(
    client, admin_headers, tmp_path
):
    zip_path = build_package(tmp_path, manifest_overrides={"course_code": OMIT})
    response = upload(client, zip_path, admin_headers)
    assert response.status_code == 422
    assert any(
        "course_code" in e and "missing" in e for e in response.json()["errors"]
    )
