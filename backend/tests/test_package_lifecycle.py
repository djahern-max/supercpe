"""Feature 038: a package version's lifecycle — delete, archive, purge media.

An unused version deletes outright; a used one archives, keeping every row
and file; once every record referencing it is past 9.02's five years, an
archived version's stored files can be purged while its rows and every
participant record stay.
"""

import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants.retention import RETENTION_YEARS
from app.models.account import Account
from app.models.attempt import Attempt, AttemptAnswer
from app.models.enrollment import Completion, Enrollment, LessonProgress, ReviewAnswer
from app.models.lesson_package import LessonPackage
from app.models.question import Question
from app.services import audit_bundle, package_lifecycle, retention
from app.services import courses as courses_service
from app.services.courses import CourseRuleViolation
from app.storage import LocalStorage
from tests.conftest import login
from tests.test_completion import make_completed
from tests.test_courses import attach, ingest, make_course, upload
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    enroll,
    make_participant,
    make_published_course,
    make_recorder,
    update_to_v2_and_republish,
)
from tests.factories.package import build_package

PACKAGES_URL = "/api/v1/admin/packages"
COURSES_URL = "/api/v1/admin/courses"


# --- helpers ----------------------------------------------------------------


def superseded_v1(db, completed=True):
    """v1 of a published course with a participant record on it, then the
    course moved to v2 — the GPT-06 shape. Returns (course, v1, v2,
    enrollment)."""
    if completed:
        course, enrollment, _attempt = make_completed(db)
        v1 = db.get(LessonPackage, int(next(iter(enrollment.package_versions))))
    else:
        course, v1 = make_published_course(db)
        enrollment = enroll(db, course, make_participant(db))
    v2 = update_to_v2_and_republish(db, course, v1)
    db.refresh(v1)
    return course, v1, v2, enrollment


def row_counts(db):
    return {
        model.__name__: db.query(model).count()
        for model in (
            Enrollment,
            Completion,
            Attempt,
            AttemptAnswer,
            ReviewAnswer,
            LessonProgress,
            Question,
            LessonPackage,
        )
    }


def freeze(monkeypatch, when):
    monkeypatch.setattr(package_lifecycle, "_now", lambda: when)


def admin(db):
    return make_recorder(db)


def put_file(storage_root, key):
    path = storage_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"video bytes")
    return path


# --- delete refuses readably -------------------------------------------------


def test_deleting_an_unused_unattached_version_removes_rows_and_files(
    client, admin_headers, storage_root, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    video = storage_root / "packages/ASC606-CON-01/v1/video.mp4"
    assert video.is_file()
    listed = client.get(PACKAGES_URL, headers=admin_headers).json()
    assert listed[0]["deletable"] is True
    assert listed[0]["retain_until"] is None

    assert client.delete(f"{PACKAGES_URL}/{package_id}", headers=admin_headers).status_code == 204
    assert not video.is_file()


def test_a_pinned_version_with_no_progress_refuses_delete_by_name(
    client, admin_headers, db_session
):
    course, v1, _v2, _enrollment = superseded_v1(db_session, completed=False)
    before = row_counts(db_session)

    response = client.delete(f"{PACKAGES_URL}/{v1.id}", headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["errors"] == [
        "package GOLD-01 v1 is referenced by 1 enrollment; archive it instead"
    ]
    assert row_counts(db_session) == before


def test_a_version_with_progress_answers_and_attempts_refuses_delete_never_500(
    client, admin_headers, db_session
):
    """GPT-06 in production: the FK path is what failed. The refusal comes
    first, so the database is never asked."""
    _course, v1, _v2, enrollment = superseded_v1(db_session)
    db_session.add(
        LessonProgress(
            enrollment_id=enrollment.id,
            package_id=v1.id,
            furthest_seconds=30,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    before = row_counts(db_session)

    response = client.delete(f"{PACKAGES_URL}/{v1.id}", headers=admin_headers)

    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "referenced by 1 enrollment" in error
    assert row_counts(db_session) == before


def test_a_preview_sitting_counts_as_a_reference(db_session):
    """Preview attempts keep their answers, which hold the questions — the
    database would refuse the delete, so the lifecycle says so first."""
    from app.services import assessment
    from tests.test_assessment import make_ready_course

    course, package = make_ready_course(db_session)
    attempt = assessment.start(db_session, course, "preview-1")
    courses_service.detach_package(db_session, course, package.id)

    usage = package_lifecycle.usage_of(db_session, package)
    assert usage.preview_attempt_ids == {attempt.id}
    assert package_lifecycle.delete_refusals(package, usage) == [
        f"package {package.lesson_id} v1 is referenced by 1 preview "
        "assessment attempt; archive it instead"
    ]


def test_the_attached_refusal_is_unchanged(client, admin_headers, tmp_path):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200
    response = client.delete(f"{PACKAGES_URL}/{package_id}", headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["errors"] == [
        "package ASC606-CON-01 v1 is attached to course ASC606-CON; "
        "detach it before deleting"
    ]


# --- archive ----------------------------------------------------------------


def test_archive_refuses_while_attached(client, admin_headers, tmp_path):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    attach(client, admin_headers, "ASC606-CON", package_id)
    response = client.post(f"{PACKAGES_URL}/{package_id}/archive", headers=admin_headers)
    assert response.status_code == 422
    assert "detach it before archiving" in response.json()["errors"][0]


def test_archived_versions_leave_the_list_unless_asked_for(
    client, admin_headers, tmp_path
):
    package_id = ingest(client, admin_headers, tmp_path)
    archived = client.post(f"{PACKAGES_URL}/{package_id}/archive", headers=admin_headers)
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    assert client.get(PACKAGES_URL, headers=admin_headers).json() == []
    [row] = client.get(
        f"{PACKAGES_URL}?include_archived=true", headers=admin_headers
    ).json()
    assert row["id"] == package_id and row["archived_at"] is not None

    again = client.post(f"{PACKAGES_URL}/{package_id}/archive", headers=admin_headers)
    assert again.status_code == 422

    restored = client.post(f"{PACKAGES_URL}/{package_id}/unarchive", headers=admin_headers)
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert len(client.get(PACKAGES_URL, headers=admin_headers).json()) == 1


def test_attach_and_update_version_refuse_an_archived_version(
    client, admin_headers, db_session, tmp_path
):
    v1_id = ingest(client, admin_headers, tmp_path, _transcript_marker="v1")
    make_course(client, admin_headers)
    assert attach(client, admin_headers, "ASC606-CON", v1_id).status_code == 200
    v2_id = ingest(client, admin_headers, tmp_path, _transcript_marker="v2")
    client.post(f"{PACKAGES_URL}/{v2_id}/archive", headers=admin_headers)

    # The course page stops offering the archived version as the update.
    detail = client.get(f"{COURSES_URL}/ASC606-CON", headers=admin_headers).json()
    assert detail["lessons"][0]["newer_version"] is None

    swap = client.post(
        f"{COURSES_URL}/ASC606-CON/lessons/{v1_id}/update-version",
        json={"new_package_id": v2_id},
        headers=admin_headers,
    )
    assert swap.status_code == 422
    assert swap.json()["errors"] == [
        "package ASC606-CON-01 v2 is archived; unarchive it before attaching it"
    ]

    client.delete(f"{COURSES_URL}/ASC606-CON/lessons/{v1_id}", headers=admin_headers)
    attached = attach(client, admin_headers, "ASC606-CON", v2_id)
    assert attached.status_code == 422
    assert "archived" in attached.json()["errors"][0]


def test_reuploading_an_archived_versions_zip_is_a_no_op_that_says_so(
    client, admin_headers, tmp_path
):
    zip_path = build_package(tmp_path)
    first = upload(client, zip_path, admin_headers)
    package_id = first.json()["package"]["id"]
    client.post(f"{PACKAGES_URL}/{package_id}/archive", headers=admin_headers)

    again = upload(client, zip_path, admin_headers)

    assert again.status_code == 200
    body = again.json()
    assert body["created"] is False
    assert body["package"]["archived_at"] is not None
    assert any("is archived" in warning for warning in body["warnings"])


# --- retain_until -----------------------------------------------------------


def test_a_completed_enrollment_anchors_on_completed_at(db_session):
    _course, v1, _v2, enrollment = superseded_v1(db_session)
    usage = package_lifecycle.usage_of(db_session, v1)
    assert usage.enrollment_ids == {enrollment.id}
    assert usage.retain_until == retention.retain_until(
        enrollment.completion.completed_at
    )


def test_an_incomplete_enrollment_anchors_on_expires_at(db_session):
    _course, v1, _v2, enrollment = superseded_v1(db_session, completed=False)
    usage = package_lifecycle.usage_of(db_session, v1)
    assert usage.retain_until == retention.retain_until(enrollment.expires_at)


def test_the_latest_record_sets_the_date(db_session):
    course, package = make_published_course(db_session)
    early = enroll(db_session, course, make_participant(db_session))
    late = enroll(
        db_session, course, make_participant(db_session, "pat2@supercpe.test")
    )
    late.expires_at = early.expires_at + timedelta(days=40)
    db_session.commit()

    usage = package_lifecycle.usage_of(db_session, package)

    assert usage.enrollment_ids == {early.id, late.id}
    assert usage.retain_until == retention.retain_until(late.expires_at)


def test_a_feb_29_anchor_retains_until_march_1(db_session):
    _course, v1, _v2, enrollment = superseded_v1(db_session, completed=False)
    enrollment.expires_at = datetime(2028, 2, 29, 12, tzinfo=timezone.utc)
    db_session.commit()
    until = package_lifecycle.usage_of(db_session, v1).retain_until
    assert until == datetime(2028 + RETENTION_YEARS, 3, 1, 12, tzinfo=timezone.utc)


# --- purge media ------------------------------------------------------------


def test_purge_refusals(db_session, storage_root):
    storage = LocalStorage(storage_root)
    course, v1, v2, _enrollment = superseded_v1(db_session)
    account = admin(db_session)

    # Attached (v2 is on the course, with a participant on it) and not
    # archived.
    enroll(db_session, course, make_participant(db_session, "pat2@supercpe.test"))
    with pytest.raises(CourseRuleViolation) as attached:
        package_lifecycle.purge_media(db_session, storage, v2, account)
    assert any("detach it before purging" in e for e in attached.value.errors)
    assert any("archive package GOLD-01 v2" in e for e in attached.value.errors)

    # Used, detached, not archived.
    with pytest.raises(CourseRuleViolation, match="archive package GOLD-01 v1"):
        package_lifecycle.purge_media(db_session, storage, v1, account)

    # Unused: delete, don't purge.
    unused = LessonPackage(**{
        **{c.name: getattr(v1, c.name) for c in LessonPackage.__table__.columns
           if c.name not in ("id", "archived_at", "media_purged_at", "media_purged_by")},
        "version": 9,
        "content_hash": "hash-unused",
        "video_key": "packages/GOLD-01/v9/video.mp4",
    })
    db_session.add(unused)
    db_session.commit()
    with pytest.raises(CourseRuleViolation, match="delete it instead"):
        package_lifecycle.purge_media(db_session, storage, unused, account)


def test_purge_waits_for_the_retention_date_to_pass(
    db_session, storage_root, monkeypatch
):
    storage = LocalStorage(storage_root)
    _course, v1, _v2, _enrollment = superseded_v1(db_session)
    package_lifecycle.archive(db_session, v1)
    until = package_lifecycle.usage_of(db_session, v1).retain_until
    video = put_file(storage_root, v1.video_key)
    before = row_counts(db_session)
    account = admin(db_session)

    freeze(monkeypatch, until - timedelta(days=1))
    with pytest.raises(CourseRuleViolation) as early:
        package_lifecycle.purge_media(db_session, storage, v1, account)
    assert early.value.errors == [
        f"the records of package GOLD-01 v1 must be retained until "
        f"{until.date().isoformat()}; its media can be purged after then"
    ]
    assert video.is_file()

    freeze(monkeypatch, until + timedelta(days=1))
    package_lifecycle.purge_media(db_session, storage, v1, account)

    assert not video.is_file()
    db_session.refresh(v1)
    assert v1.media_purged_at == until + timedelta(days=1)
    assert v1.media_purged_by == account.email
    # Nothing but the file went.
    assert row_counts(db_session) == before

    with pytest.raises(CourseRuleViolation, match="already purged"):
        package_lifecycle.purge_media(db_session, storage, v1, account)
    with pytest.raises(CourseRuleViolation, match="stays archived"):
        package_lifecycle.unarchive(db_session, v1)


def test_purge_deletes_every_owned_media_file_of_a_text_package(
    db_session, storage_root, tmp_path, monkeypatch
):
    from tests.test_text_packages import ingest_text

    package, _ = ingest_text(db_session, storage_root, tmp_path)
    keys = package_lifecycle.owned_keys(package)
    assert keys and all((storage_root / key).is_file() for key in keys)
    course = courses_service.create_course(db_session, "TXT-1", "Text")
    package.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    # A record referencing it, well past retention.
    enrollment = Enrollment(
        account_id=make_participant(db_session).id,
        course_id=course.id,
        enrolled_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2001, 1, 1, tzinfo=timezone.utc),
        source="admin",
        package_versions={str(package.id): package.version},
    )
    db_session.add(enrollment)
    db_session.commit()

    package_lifecycle.purge_media(
        db_session, LocalStorage(storage_root), package, admin(db_session)
    )

    assert not any((storage_root / key).is_file() for key in keys)


def test_purge_over_the_api_and_the_list_says_when(
    client, admin_headers, db_session, monkeypatch
):
    _course, v1, _v2, _enrollment = superseded_v1(db_session)
    until = package_lifecycle.usage_of(db_session, v1).retain_until

    assert client.post(f"{PACKAGES_URL}/{v1.id}/archive", headers=admin_headers).status_code == 200
    [row] = [
        r
        for r in client.get(
            f"{PACKAGES_URL}?include_archived=true", headers=admin_headers
        ).json()
        if r["id"] == v1.id
    ]
    assert row["enrollment_count"] == 1
    assert row["deletable"] is False
    assert row["media_purgeable"] is False
    assert datetime.fromisoformat(row["retain_until"]) == until

    early = client.post(f"{PACKAGES_URL}/{v1.id}/purge-media", headers=admin_headers)
    assert early.status_code == 422

    freeze(monkeypatch, until + timedelta(seconds=1))
    done = client.post(f"{PACKAGES_URL}/{v1.id}/purge-media", headers=admin_headers)
    assert done.status_code == 200, done.text
    assert done.json()["media_purged_at"] is not None
    assert done.json()["media_purged_by"] is not None
    # The detail still serves the transcript and questions.
    detail = client.get(f"{PACKAGES_URL}/{v1.id}", headers=admin_headers).json()
    assert detail["questions"] and detail["manifest"]
    assert client.get(f"{PACKAGES_URL}/{v1.id}/transcript", headers=admin_headers).status_code == 200


# --- after purge ------------------------------------------------------------


def mark_purged(db, package):
    now = datetime.now(timezone.utc)
    package.archived_at = now
    package.media_purged_at = datetime(2033, 3, 1, tzinfo=timezone.utc)
    package.media_purged_by = "admin@supercpe.test"
    db.commit()


REMOVED = (
    "Materials for this version were removed on 2033-03-01 after the "
    "retention period."
)


def test_the_participant_player_says_the_video_was_removed(client, db_session):
    _course, v1, _v2, enrollment = superseded_v1(db_session)
    mark_purged(db_session, v1)
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)

    response = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/lessons/{v1.id}/play"
    )

    assert response.status_code == 410
    assert response.json() == {"errors": [REMOVED]}


def test_the_reader_keeps_the_guide_and_says_the_media_were_removed(
    client, db_session, storage_root, tmp_path
):
    from tests.test_text_packages import (
        ingest_text,
        make_publishable_text_course,
    )

    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = make_publishable_text_course(db_session, package)
    courses_service.publish(db_session, course)
    enrollment = enroll(db_session, course, make_participant(db_session))
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    url = f"/api/v1/my/enrollments/{enrollment.id}/lessons/{package.id}/read"
    assert client.get(url).json()["media_removed"] is None

    mark_purged(db_session, package)
    body = client.get(url).json()

    assert body["media"] == []
    assert body["media_removed"] == REMOVED
    assert any(s["markdown"] for s in body["sections"])
    assert body["questions"]


def test_the_audit_bundle_names_the_removal_instead_of_the_key(
    db_session, storage_root
):
    course, enrollment, _attempt = make_completed(db_session)
    package = db_session.get(
        LessonPackage, int(next(iter(enrollment.package_versions)))
    )
    put_file(storage_root, package.video_key)
    mark_purged(db_session, package)
    generated_by = db_session.query(Account).filter_by(role="admin").first()

    content, _manifest = audit_bundle.build(
        db_session,
        LocalStorage(storage_root),
        course,
        generated_by,
        include_video=True,
    )

    archive = zipfile.ZipFile(io.BytesIO(content))
    names = archive.namelist()
    [video_txt] = [n for n in names if n.endswith("GOLD-01/v1/video.txt")]
    assert REMOVED in archive.read(video_txt).decode()
    assert not any(n.endswith("GOLD-01/v1/video.mp4") for n in names)
    assert any(n.endswith("GOLD-01/v1/transcript.md") for n in names)


# --- constraints ------------------------------------------------------------


def test_a_purge_must_name_its_admin(db_session):
    course, package = make_published_course(db_session)
    package.archived_at = datetime.now(timezone.utc)
    package.media_purged_at = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError, match="ck_lesson_packages_purge_names_admin"):
        db_session.commit()
    db_session.rollback()


def test_only_an_archived_version_can_be_purged(db_session):
    course, package = make_published_course(db_session)
    package.media_purged_at = datetime.now(timezone.utc)
    package.media_purged_by = "admin@supercpe.test"
    with pytest.raises(
        IntegrityError, match="ck_lesson_packages_purge_requires_archive"
    ):
        db_session.commit()
    db_session.rollback()
