"""Feature 011: the per-course audit bundle (9.02.2), the retention
constant, and the Unicode certificate font.

The scenario the spec fixes: a course with two enrollments, one
completion, one failed attempt, one evaluation, two evaluation reviews,
and a package updated once — so two package versions are pinned somewhere
and both must appear under 7-materials.
"""

import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone

from app.constants.retention import RETENTION_YEARS
from app.services import development, evaluations, retention
from app.services import courses as courses_service
from app.services import questions as questions_service
from tests.conftest import login, make_account
from tests.test_completion import complete_profile, sit
from tests.test_credit import make_package_row
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    answer_all_reviews,
    enroll,
    make_participant,
    make_published_course,
    make_recorder,
    make_sme,
)
from tests.test_evaluations import GOOD_RATINGS
from tests.test_questions import questions_of


# --- retention --------------------------------------------------------------


def test_retain_until_is_exactly_retention_years_after_completion():
    completed = datetime(2026, 8, 29, 15, 30, tzinfo=timezone.utc)
    assert retention.retain_until(completed) == datetime(
        2026 + RETENTION_YEARS, 8, 29, 15, 30, tzinfo=timezone.utc
    )
    # A Feb 29 completion retains until Mar 1 of the non-leap year.
    leap = datetime(2028, 2, 29, tzinfo=timezone.utc)
    assert retention.retain_until(leap) == datetime(
        2028 + RETENTION_YEARS, 3, 1, tzinfo=timezone.utc
    )


def test_admin_completions_carry_retain_until(client, admin_headers, db_session):
    from tests.test_completion import make_completed

    course, enrollment, _ = make_completed(db_session)
    [row] = client.get(
        f"/api/v1/admin/courses/{course.course_code}/completions",
        headers=admin_headers,
    ).json()
    expected = retention.retain_until(enrollment.completion.completed_at)
    assert (
        datetime.fromisoformat(row["retain_until"].replace("Z", "+00:00"))
        == expected
    )


# --- the bundle scenario ----------------------------------------------------


def build_scenario(client, db_session):
    """Two enrollments, one completion (certificate rendered), one failed
    attempt, one evaluation, two evaluation reviews, a package updated
    once, and the three policies published."""
    complete_profile(db_session)
    course, package_v1 = make_published_course(db_session)

    # Participant A completes on v1, downloads the certificate (renders and
    # stores it), and evaluates.
    pat = make_participant(db_session)
    enrollment_a = enroll(db_session, course, pat)
    answer_all_reviews(db_session, enrollment_a)
    attempt = sit(db_session, enrollment_a)
    assert attempt.status == "passed"
    completion = enrollment_a.completion
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    assert (
        client.get(
            f"/api/v1/my/completions/{completion.id}/certificate.pdf"
        ).status_code
        == 200
    )
    evaluations.submit(
        db_session, completion, GOOD_RATINGS, comments="Learned a lot."
    )

    # Two 4.04.2 reviews of the results.
    admin = make_recorder(db_session)
    evaluations.record_review(db_session, course, admin, "First look.", False)
    evaluations.record_review(
        db_session, course, admin, "Told the developer.", True
    )

    # The package is updated once: v2 swaps in through
    # unpublish -> update-version -> re-review -> republish.
    package_v2 = make_package_row(
        db_session,
        lesson_id=package_v1.lesson_id,
        version=2,
        duration_seconds=900,
        questions=questions_of(review=2, assessment=4),
    )
    questions_service.normalize(db_session, package_v2)
    db_session.commit()
    courses_service.unpublish(db_session, course)
    courses_service.update_version(
        db_session, course, package_v1.id, package_v2.id
    )
    reviewer = make_sme(db_session, "Second Rev CPA")
    development.record_review(
        db_session,
        course,
        reviewer.id,
        date.today(),
        "approved",
        recorded_by=admin,
    )
    courses_service.publish(db_session, course)

    # Participant B enrolls on v2 and fails an attempt.
    kim = make_participant(db_session, email="kim@supercpe.test")
    enrollment_b = enroll(db_session, course, kim)
    answer_all_reviews(db_session, enrollment_b)
    failed = sit(db_session, enrollment_b, wrong=4)
    assert failed.status == "failed"

    # The three policies were published by make_published_course — since
    # 016 nothing publishes without them.
    return course, completion, package_v1, package_v2


EXPECTED_FILES = [
    "README.md",
    "bundle.json",
    "1-completion/completions.csv",
    "1-completion/attempts.csv",
    "1-completion/attempt_answers.csv",
    "1-completion/review_answers.csv",
    "2-credit/calculation.txt",
    "2-credit/credit_breakdown.json",
    "3-expiration/enrollments.csv",
    "3-expiration/policy.txt",
    "4-people/developer.json",
    "4-people/reviewers.json",
    "4-people/reviews.csv",
    "4-people/review_cycle.txt",
    "5-evaluations/evaluations.csv",
    "5-evaluations/summary.json",
    "5-evaluations/evaluation_reviews.csv",
    "6-descriptive/course.json",
    "6-descriptive/course.md",
    "6-descriptive/policies/registration-1.md",
    "6-descriptive/policies/refund-1.md",
    "6-descriptive/policies/complaint-1.md",
    "6-descriptive/how-it-works.md",
]


def unzip(content: bytes) -> dict[str, bytes]:
    """Strip the single top-level directory and return path -> bytes."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    tops = {name.split("/", 1)[0] for name in archive.namelist()}
    assert len(tops) == 1
    return {
        name.split("/", 1)[1]: archive.read(name)
        for name in archive.namelist()
    }


def test_bundle_layout_manifest_and_log(client, admin_headers, db_session):
    course, completion, package_v1, package_v2 = build_scenario(
        client, db_session
    )
    from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    generated = client.post(
        f"/api/v1/admin/courses/{course.course_code}/audit-bundle",
        json={"include_video": False},
    )
    assert generated.status_code == 201, generated.json()
    export = generated.json()

    downloaded = client.get(
        f"/api/v1/admin/courses/{course.course_code}/audit-bundle/"
        f"{export['id']}.zip"
    )
    assert downloaded.status_code == 200
    content = downloaded.content

    # The logged sha256 is the sha256 of the returned bytes.
    assert export["sha256"] == hashlib.sha256(content).hexdigest()
    assert export["size_bytes"] == len(content)
    assert export["storage_key"].startswith(
        f"audits/{course.course_code}/"
    )

    files = unzip(content)
    for path in EXPECTED_FILES:
        assert path in files, f"missing {path}"

    # Both package versions ever pinned are present; videos by reference.
    for package in (package_v1, package_v2):
        prefix = f"7-materials/{package.lesson_id}/v{package.version}"
        for name in ("manifest.json", "questions.json", "transcript.md", "video.txt"):
            assert f"{prefix}/{name}" in files
        video_note = files[f"{prefix}/video.txt"].decode()
        assert package.video_key in video_note
        assert "video omitted" in video_note
        assert f"{prefix}/video.mp4" not in files

    # bundle.json lists every file with a matching sha256, and every file
    # except itself is listed.
    manifest = json.loads(files["bundle.json"])
    listed = {entry["path"]: entry for entry in manifest["files"]}
    assert set(listed) == set(files) - {"bundle.json"}
    for path, entry in listed.items():
        assert entry["sha256"] == hashlib.sha256(files[path]).hexdigest()
        assert entry["size_bytes"] == len(files[path])
    assert manifest["course_code"] == course.course_code
    assert manifest["generated_by"] == ADMIN_EMAIL

    # completions.csv: exactly one row, the right credit and certificate.
    lines = files["1-completion/completions.csv"].decode().strip().splitlines()
    assert len(lines) == 2  # header + one completion
    assert str(completion.credit_awarded) in lines[1]
    assert completion.certificate_number in lines[1]
    assert (
        retention.retain_until(completion.completed_at).isoformat()
        in lines[1]
    )

    # The rendered certificate and its snapshot are inside.
    assert (
        f"1-completion/certificates/{completion.certificate_number}.pdf"
        in files
    )
    snapshot = json.loads(
        files[f"1-completion/certificates/{completion.certificate_number}.json"]
    )
    assert snapshot == completion.certificate_snapshot

    # attempts.csv holds the pass and the fail.
    attempts_csv = files["1-completion/attempts.csv"].decode()
    assert "passed" in attempts_csv and "failed" in attempts_csv

    # 9.02.2(4): the bundle is the one place license numbers may appear.
    reviewers = json.loads(files["4-people/reviewers.json"])
    assert len(reviewers) == 2
    assert all(r["license_number"] == "12345" for r in reviewers)
    developer = json.loads(files["4-people/developer.json"])
    assert developer["license_number"] == "12345"
    assert developer["developer_used_technology"] is True

    # Evaluations: the rows, the quoted prompts, and the 4.04.2 log.
    evaluations_csv = files["5-evaluations/evaluations.csv"].decode()
    assert "Were the stated learning objectives met?" in evaluations_csv
    assert "Learned a lot." in evaluations_csv
    review_lines = (
        files["5-evaluations/evaluation_reviews.csv"].decode().strip().splitlines()
    )
    assert len(review_lines) == 3  # header + two reviews
    assert json.loads(files["5-evaluations/summary.json"])["n"] == 1

    # README maps the seven elements and states the registry truth; no
    # other descriptive file mentions the Registry.
    readme = files["README.md"].decode()
    for locator in [f"9.02.2({n})" for n in range(1, 8)]:
        assert locator in readme
    assert "not on the National Registry" in readme
    assert str(RETENTION_YEARS) in readme
    for path in files:
        if path.startswith("6-descriptive/"):
            assert "National Registry" not in files[path].decode(), path

    # The credit record re-states 005's written-out calculation.
    assert "Recommended CPE credit" in files["2-credit/calculation.txt"].decode()
    assert json.loads(files["2-credit/credit_breakdown.json"]) != []


def test_second_generation_adds_a_row_and_preserves_the_first(
    client, admin_headers, db_session, storage_root
):
    course, *_ = build_scenario(client, db_session)
    from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    url = f"/api/v1/admin/courses/{course.course_code}/audit-bundle"
    first = client.post(url, json={"include_video": False}).json()
    first_bytes = (storage_root / first["storage_key"]).read_bytes()

    second = client.post(url, json={"include_video": False}).json()
    assert second["id"] != first["id"]
    assert second["storage_key"] != first["storage_key"]

    # The first export's stored zip is untouched.
    assert (storage_root / first["storage_key"]).read_bytes() == first_bytes

    history = client.get(url).json()
    assert [row["id"] for row in history] == [second["id"], first["id"]]


def test_include_video_zips_the_stored_mp4(
    client, admin_headers, db_session, storage_root
):
    course, _, package_v1, package_v2 = build_scenario(client, db_session)
    from app.storage import LocalStorage
    from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

    storage = LocalStorage(storage_root)
    storage.put(package_v2.video_key, io.BytesIO(b"fake mp4 bytes"))

    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    export = client.post(
        f"/api/v1/admin/courses/{course.course_code}/audit-bundle",
        json={"include_video": True},
    ).json()
    content = client.get(
        f"/api/v1/admin/courses/{course.course_code}/audit-bundle/"
        f"{export['id']}.zip"
    ).content
    files = unzip(content)
    prefix = f"7-materials/{package_v2.lesson_id}/v{package_v2.version}"
    assert files[f"{prefix}/video.mp4"] == b"fake mp4 bytes"
    # v1's video was never stored in this test's storage; it stays by
    # reference.
    assert (
        f"7-materials/{package_v1.lesson_id}/v{package_v1.version}/video.mp4"
        not in files
    )
