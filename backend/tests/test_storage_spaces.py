"""SpacesStorage and the backup upload/retention against moto's
in-process S3. moto intercepts AWS endpoints only, so the test client
points at s3.amazonaws.com; the code under test is identical either way —
the endpoint is configuration."""

import io
from datetime import date
from pathlib import Path

import pytest
from moto import mock_aws

from app.constants.storage import (
    BACKUP_KEEP_RECENT,
    BACKUP_LATEST_KEY,
    HEALTH_SENTINEL_KEY,
    VIDEO_URL_SECONDS,
)
from app.services import backups
from app.storage import LocalStorage, SpacesStorage

BUCKET = "supercpe-test"


@pytest.fixture
def spaces():
    with mock_aws():
        storage = SpacesStorage(
            bucket=BUCKET,
            region="us-east-1",
            endpoint="https://s3.amazonaws.com",
            key="testing",
            secret="testing",
        )
        storage.client.create_bucket(Bucket=BUCKET)
        yield storage


def test_round_trip(spaces):
    spaces.put("packages/lesson.zip", io.BytesIO(b"zip bytes"))
    assert spaces.exists("packages/lesson.zip")
    with spaces.open("packages/lesson.zip") as obj:
        assert obj.read() == b"zip bytes"
    spaces.delete("packages/lesson.zip")
    assert not spaces.exists("packages/lesson.zip")


def test_exists_is_false_for_missing_key(spaces):
    assert not spaces.exists("packages/never-written.zip")


def test_url_for_is_a_signed_expiring_url(spaces):
    url = spaces.url_for("packages/lesson.mp4", VIDEO_URL_SECONDS)
    assert "packages/lesson.mp4" in url
    assert f"X-Amz-Expires={VIDEO_URL_SECONDS}" in url
    assert "X-Amz-Signature=" in url


def test_put_sets_content_type(spaces):
    spaces.put("packages/lesson.mp4", io.BytesIO(b"x"))
    head = spaces.client.head_object(Bucket=BUCKET, Key="packages/lesson.mp4")
    assert head["ContentType"] == "video/mp4"

    spaces.put(HEALTH_SENTINEL_KEY, io.BytesIO(b"ok"))
    head = spaces.client.head_object(Bucket=BUCKET, Key=HEALTH_SENTINEL_KEY)
    assert head["ContentType"] == "application/octet-stream"


def test_put_never_grants_a_public_acl(spaces):
    spaces.put("certificates/1.pdf", io.BytesIO(b"pdf"))
    acl = spaces.client.get_object_acl(Bucket=BUCKET, Key="certificates/1.pdf")
    for grant in acl["Grants"]:
        assert grant["Grantee"].get("URI") != (
            "http://acs.amazonaws.com/groups/global/AllUsers"
        )


def test_local_url_for_is_the_media_route(tmp_path):
    storage = LocalStorage(tmp_path)
    assert (
        storage.url_for("packages/lesson.mp4", VIDEO_URL_SECONDS)
        == "/api/v1/media/packages/lesson.mp4"
    )


def test_backup_upload_writes_dump_and_latest(spaces, tmp_path):
    dump = tmp_path / "2026-08-29.dump.gz"
    dump.write_bytes(b"pg dump bytes")

    key = backups.upload(spaces, dump)

    assert key == "backups/2026-08-29.dump.gz"
    with spaces.open(key) as obj:
        assert obj.read() == b"pg dump bytes"
    with spaces.open(BACKUP_LATEST_KEY) as obj:
        stamp, latest_key = obj.read().decode().splitlines()
    assert latest_key == key
    # The stamp is what /health reports as last_backup_at.
    assert stamp.startswith("20")


def test_backup_upload_refuses_a_misnamed_file(spaces, tmp_path):
    stray = tmp_path / "database.dump.gz"
    stray.write_bytes(b"x")
    with pytest.raises(ValueError):
        backups.upload(spaces, stray)


def test_retention_keeps_recent_and_monthly_firsts():
    # Daily dumps 2026-05-01 .. 2026-08-29 (121). The newest 90 reach
    # back exactly to 2026-06-01, so May is "beyond": its first dump
    # stays forever, the other 30 are prunable.
    days = [
        date.fromordinal(ordinal)
        for ordinal in range(
            date(2026, 5, 1).toordinal(), date(2026, 8, 29).toordinal() + 1
        )
    ]
    assert len(days) == BACKUP_KEEP_RECENT + 31

    prunable = backups.prunable_keys(days)

    assert date(2026, 5, 1) not in prunable
    assert date(2026, 6, 1) not in prunable
    assert set(prunable) == {date(2026, 5, day) for day in range(2, 32)}


def test_retention_prunes_nothing_under_the_recent_window():
    days = [date(2026, 8, day) for day in range(1, 30)]
    assert backups.prunable_keys(days) == []


def test_backup_upload_prunes(spaces, tmp_path, monkeypatch):
    # A tiny retention window keeps the test legible; the real number is
    # asserted against directly in the retention tests above.
    monkeypatch.setattr(backups, "BACKUP_KEEP_RECENT", 2)
    for day in ("2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"):
        dump = tmp_path / f"{day}.dump.gz"
        dump.write_bytes(b"x")
        backups.upload(spaces, dump)

    assert spaces.exists("backups/2026-06-04.dump.gz")
    assert spaces.exists("backups/2026-06-03.dump.gz")
    # June's first dump survives as the monthly keeper; the second is gone.
    assert spaces.exists("backups/2026-06-01.dump.gz")
    assert not spaces.exists("backups/2026-06-02.dump.gz")
