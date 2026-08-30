"""deploy/bucket-setup.py against moto (acceptance 2 of 013): enables
versioning, sets exactly one lifecycle rule, is idempotent, and exits
non-zero when the read-back disagrees. The read-back against the real
bucket — the proof DigitalOcean honors NoncurrentVersionExpiration with
a prefix — is the operator's acceptance walkthrough."""

import importlib.util
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.constants.storage import BACKUP_NONCURRENT_DAYS, BACKUPS_PREFIX

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "bucket-setup.py"
spec = importlib.util.spec_from_file_location("bucket_setup", SCRIPT)
bucket_setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bucket_setup)

BUCKET = "supercpe-test"


@pytest.fixture
def client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_setup_enables_versioning_and_the_one_rule(client):
    assert bucket_setup.setup(client, BUCKET) == 0

    assert client.get_bucket_versioning(Bucket=BUCKET)["Status"] == "Enabled"
    rules = client.get_bucket_lifecycle_configuration(Bucket=BUCKET)["Rules"]
    assert len(rules) == 1
    assert bucket_setup.rule_prefix(rules[0]) == BACKUPS_PREFIX
    assert rules[0]["NoncurrentVersionExpiration"]["NoncurrentDays"] == (
        BACKUP_NONCURRENT_DAYS
    )
    # The one rule expires noncurrent backup versions and nothing else:
    # no Expiration action that could touch current 9.02 objects.
    assert "Expiration" not in rules[0]


def test_setup_is_idempotent(client, capsys):
    assert bucket_setup.setup(client, BUCKET) == 0
    first = capsys.readouterr().out
    assert bucket_setup.setup(client, BUCKET) == 0
    second = capsys.readouterr().out
    assert first == second
    rules = client.get_bucket_lifecycle_configuration(Bucket=BUCKET)["Rules"]
    assert len(rules) == 1


class ReadBackLies:
    """A client whose read-back never shows versioning Enabled, as a
    provider that silently ignored PutBucketVersioning would."""

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    def get_bucket_versioning(self, **kwargs):
        return {}


def test_setup_exits_nonzero_when_readback_fails(client, capsys):
    assert bucket_setup.setup(ReadBackLies(client), BUCKET) == 1
    assert "FAILED" in capsys.readouterr().err
