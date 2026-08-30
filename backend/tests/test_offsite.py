"""The off-site mirror (013): a second S3-compatible bucket at a second
provider holding the nightly dumps and the small retained prefixes.
Both buckets live in moto's in-process S3; the second provider is the
second bucket — the code under test only ever sees two clients."""

import io
from datetime import date, datetime, timezone

import pytest
from moto import mock_aws

from app import cli
from app.constants.storage import (
    BACKUP_LATEST_KEY,
    MIRRORED_PREFIXES,
    OFFSITE_STAMP_KEY,
)
from app.services import backups
from app.services import offsite as offsite_service
from app.storage import SpacesStorage

PRIMARY_BUCKET = "supercpe-primary"
OFFSITE_BUCKET = "supercpe-offsite"


def make_storage(bucket):
    storage = SpacesStorage(
        bucket=bucket,
        region="us-east-1",
        endpoint="https://s3.amazonaws.com",
        key="testing",
        secret="testing",
    )
    storage.client.create_bucket(Bucket=bucket)
    return storage


@pytest.fixture
def buckets():
    with mock_aws():
        yield make_storage(PRIMARY_BUCKET), make_storage(OFFSITE_BUCKET)


def upload_dump(primary, tmp_path, day):
    dump = tmp_path / f"{day.isoformat()}.dump.gz"
    dump.write_bytes(b"pg dump bytes")
    backups.upload(primary, dump)


def test_mirror_backup_copies_the_dump_and_stamps_latest(buckets, tmp_path):
    primary, offsite = buckets
    day = date(2026, 8, 30)
    upload_dump(primary, tmp_path, day)

    key = offsite_service.mirror_backup(primary, offsite, day)

    assert key == "backups/2026-08-30.dump.gz"
    with offsite.open(key) as obj:
        assert obj.read() == b"pg dump bytes"
    # LATEST off-site carries the primary's own stamp, so the two buckets
    # agree on what the newest dump is.
    with primary.open(BACKUP_LATEST_KEY) as obj:
        primary_latest = obj.read()
    with offsite.open(BACKUP_LATEST_KEY) as obj:
        assert obj.read() == primary_latest


def test_mirror_prefix_copies_missing_and_changed_objects(buckets):
    primary, offsite = buckets
    primary.put("certificates/0001.pdf", io.BytesIO(b"pdf one"))
    primary.put("certificates/0002.pdf", io.BytesIO(b"pdf two"))

    assert offsite_service.mirror_prefix(primary, offsite, "certificates/") == 2
    with offsite.open("certificates/0001.pdf") as obj:
        assert obj.read() == b"pdf one"

    # Idempotent: an unchanged prefix copies nothing on the next run.
    assert offsite_service.mirror_prefix(primary, offsite, "certificates/") == 0

    # A changed object (write-once discipline should prevent this, but
    # the mirror must not trust it) is re-copied.
    primary.put("certificates/0001.pdf", io.BytesIO(b"pdf one corrected"))
    assert offsite_service.mirror_prefix(primary, offsite, "certificates/") == 1
    with offsite.open("certificates/0001.pdf") as obj:
        assert obj.read() == b"pdf one corrected"


def test_mirror_prefix_never_deletes_offsite(buckets):
    primary, offsite = buckets
    # An object that exists only off-site (say the primary lost it — the
    # exact disaster the mirror is for) must survive every run untouched.
    offsite.put("audits/only-offsite.zip", io.BytesIO(b"survivor"))
    primary.put("audits/current.zip", io.BytesIO(b"zip"))

    offsite_service.mirror_prefix(primary, offsite, "audits/")

    assert offsite.exists("audits/only-offsite.zip")
    assert offsite.exists("audits/current.zip")


def test_cli_mirror_offsite_stamps_the_primary_on_success(
    buckets, tmp_path, monkeypatch, capsys
):
    primary, offsite = buckets
    day = date(2026, 8, 30)
    upload_dump(primary, tmp_path, day)
    primary.put("certificates/0001.pdf", io.BytesIO(b"pdf"))
    primary.put("audits/bundle.zip", io.BytesIO(b"zip"))
    monkeypatch.setattr(cli, "get_storage", lambda: primary)
    monkeypatch.setattr(offsite_service, "get_offsite", lambda: offsite)

    assert cli.mirror_offsite("2026-08-30") == 0

    for prefix in MIRRORED_PREFIXES:
        listing = offsite.client.list_objects_v2(
            Bucket=OFFSITE_BUCKET, Prefix=prefix
        )
        assert listing["KeyCount"] == 1
    with primary.open(OFFSITE_STAMP_KEY) as stamp:
        stamped = datetime.fromisoformat(stamp.read().decode().splitlines()[0])
    assert abs((datetime.now(timezone.utc) - stamped).total_seconds()) < 60


def test_cli_mirror_offsite_is_a_noop_while_unconfigured(
    buckets, monkeypatch, capsys
):
    primary, _ = buckets
    monkeypatch.setattr(cli, "get_storage", lambda: primary)
    # The default test settings carry no OFFSITE_*, so get_offsite is
    # None through the real code path.
    assert cli.mirror_offsite(None) == 0
    assert "not configured" in capsys.readouterr().out
    assert not primary.exists(OFFSITE_STAMP_KEY)


def test_cli_mirror_offsite_failure_is_nonzero_and_named(
    buckets, tmp_path, monkeypatch, capsys
):
    """Acceptance 4: the primary LATEST is already stamped when the
    off-site step fails, so the failure exits non-zero and names the
    off-site step without masking the primary as the problem."""
    primary, _ = buckets
    day = date(2026, 8, 30)
    upload_dump(primary, tmp_path, day)
    dead = SpacesStorage(
        bucket="no-such-bucket",
        region="us-east-1",
        endpoint="https://s3.amazonaws.com",
        key="testing",
        secret="testing",
    )
    monkeypatch.setattr(cli, "get_storage", lambda: primary)
    monkeypatch.setattr(offsite_service, "get_offsite", lambda: dead)

    assert cli.mirror_offsite("2026-08-30") == 1

    assert "off-site mirror failed" in capsys.readouterr().err
    assert primary.exists(BACKUP_LATEST_KEY)
    assert not primary.exists(OFFSITE_STAMP_KEY)
