"""Feature 023a: manifest.json joins the content hash.

Ingest deduplicates on `content_hash`. Until 023a the hash covered the
transcript, questions and video (video kind) or the sections, questions
and media (text kind) — never the manifest — so a re-upload whose only
change was a manifest field was answered "Already ingested — nothing was
created … unchanged," which was false: it had changed, and the change was
discarded. Since the manifest carries `word_count`, section `role`s, and
every 8.01 descriptor, the discarded change could be a credit input.

These are the acceptance criteria of current-feature.md, in order.
"""

import json

from app.services import courses as courses_service
from app.services import credit, packages
from app.services.packages import manifest_hash_bytes
from app.services.word_count import count_words
from tests.factories.package import (
    DEFAULT_COURSE_CODE as VIDEO_COURSE_CODE,
)
from tests.factories.package import build_package
from tests.factories.text_package import (
    APPENDIX,
    DEFAULT_SECTION_FILES,
    build_text_package,
    default_sections,
)

PACKAGES_URL = "/api/v1/admin/packages"


def upload(client, zip_path, headers):
    with open(zip_path, "rb") as f:
        return client.post(
            PACKAGES_URL,
            files={"file": ("package.zip", f, "application/zip")},
            headers=headers,
        )


# --- 1. a byte-identical re-upload is still a no-op ------------------------


def test_identical_video_reupload_is_still_unchanged(
    client, admin_headers, tmp_path
):
    zip_path = build_package(tmp_path)
    first = upload(client, zip_path, admin_headers)
    assert first.status_code == 201

    second = upload(client, zip_path, admin_headers)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["package"]["id"] == first.json()["package"]["id"]


def test_identical_text_reupload_is_still_unchanged(
    client, admin_headers, tmp_path
):
    zip_path = build_text_package(tmp_path)
    first = upload(client, zip_path, admin_headers)
    assert first.status_code == 201

    second = upload(client, zip_path, admin_headers)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["package"]["id"] == first.json()["package"]["id"]


# --- 2. a text section role flip is a new version --------------------------


def test_role_flip_alone_creates_a_new_version_and_moves_the_word_count(
    client, admin_headers, tmp_path
):
    """appendix -> body, with every file in the zip byte-identical. This is
    the case the old hash could not see, and it is a credit input: 7.02.5
    counts body sections and excludes appendixes, so the flip moves the
    computed word count and therefore the course's credit."""
    first = upload(client, build_text_package(tmp_path), admin_headers)
    assert first.status_code == 201, first.text
    v1 = first.json()["package"]

    flipped = default_sections()
    appendix = next(s for s in flipped if s["id"] == "sec-91")
    assert appendix["role"] == "appendix"
    appendix["role"] = "body"

    second = upload(
        client,
        build_text_package(tmp_path, manifest_overrides={"sections": flipped}),
        admin_headers,
    )
    assert second.status_code == 201, second.text
    v2 = second.json()["package"]

    assert second.json()["created"] is True
    assert v2["version"] == v1["version"] + 1
    assert v2["content_hash"] != v1["content_hash"]

    # The only difference between the two zips is that one manifest word.
    assert v2["word_count"] == v1["word_count"] + count_words(APPENDIX)
    roles = {s["section_key"]: s["role"] for s in v2["sections"]}
    assert roles["sec-91"] == "body"


def test_the_flipped_zip_is_otherwise_byte_identical(tmp_path):
    """Guards the test above: if the two fixtures differed in a file, the
    new version would prove nothing about the manifest."""
    flipped = default_sections()
    next(s for s in flipped if s["id"] == "sec-91")["role"] = "body"

    plain = packages.validate(build_text_package(tmp_path))
    changed = packages.validate(
        build_text_package(tmp_path, manifest_overrides={"sections": flipped})
    )
    assert not isinstance(plain, list), plain
    assert not isinstance(changed, list), changed

    # Every hashed file is identical between the two packages...
    assert [s.file for s in changed.sections] == [s.file for s in plain.sections]
    assert [s.markdown for s in changed.sections] == [
        DEFAULT_SECTION_FILES[s.file] for s in plain.sections
    ]
    assert changed.questions == plain.questions
    assert [m.file for m in changed.media] == [m.file for m in plain.media]

    # ...and the manifests differ in exactly one word, plus the hash the
    # word moved.
    differing = {
        key
        for key in set(plain.manifest) | set(changed.manifest)
        if plain.manifest.get(key) != changed.manifest.get(key)
    }
    assert differing == {"sections", "content_hash"}
    assert changed.content_hash != plain.content_hash


# --- 3. a video manifest word_count change is a new version ----------------


def test_word_count_change_alone_creates_a_new_version_and_moves_credit(
    client, admin_headers, db_session, tmp_path
):
    """A video lesson that narrates its own text counts by its words
    (7.02.7), so `word_count` is a live credit input that lives only in the
    manifest. Changing it must reach the course."""
    reads = {"av_is_additional_learning": False, "word_count": 1800}
    first = upload(
        client, build_package(tmp_path, manifest_overrides=reads), admin_headers
    )
    assert first.status_code == 201, first.text
    v1 = first.json()["package"]

    course = courses_service.create_course(
        db_session, VIDEO_COURSE_CODE, "Revenue Under ASC 606"
    )
    courses_service.attach_package(db_session, course, v1["id"])
    db_session.refresh(course)
    assert course.credit_word_count == 1800
    award_before = course.credit_award

    second = upload(
        client,
        build_package(
            tmp_path, manifest_overrides={**reads, "word_count": 5400}
        ),
        admin_headers,
    )
    assert second.status_code == 201, second.text
    v2 = second.json()["package"]
    assert v2["version"] == v1["version"] + 1
    assert v2["word_count"] == 5400

    courses_service.update_version(db_session, course, v1["id"], v2["id"])
    db_session.refresh(course)
    assert course.credit_word_count == 5400
    assert course.credit_award > award_before
    assert not credit.is_stale(course)


# --- 4. the canonical manifest bytes are what docs/course-package.md says --


def test_the_hash_excludes_content_hash_and_ignores_formatting(tmp_path):
    """The two properties the contract names: the digest cannot cover its
    own field, and what is hashed is the parsed object in canonical form,
    so indentation and key order in the written file move nothing."""
    manifest = {"b": 1, "a": {"y": "é", "x": [1, 2]}, "content_hash": "abc"}

    assert manifest_hash_bytes(manifest) == (
        '{"a":{"x":[1,2],"y":"é"},"b":1}'.encode("utf-8")
    )
    # Same object, different written form, different declared hash.
    reordered = json.loads(
        json.dumps(manifest, indent=4, sort_keys=True).replace(
            '"abc"', '"0000"'
        )
    )
    assert manifest_hash_bytes(reordered) == manifest_hash_bytes(manifest)
    # And a real change moves it.
    assert manifest_hash_bytes({**manifest, "b": 2}) != manifest_hash_bytes(
        manifest
    )


def test_the_factory_writes_a_hash_the_ingester_recomputes(tmp_path):
    """The fixture factory computes the hash the way an exporter must —
    before the field exists — and ingest agrees on both kinds."""
    for zip_path in (build_package(tmp_path), build_text_package(tmp_path)):
        result = packages.validate(zip_path)
        assert not isinstance(result, list), result
        assert result.manifest["content_hash"] == result.content_hash
