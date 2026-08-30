"""`python -m app.cli bucket-setup` against moto (013's script tests,
ported by 014a when the logic moved into app.cli): enables versioning,
sets exactly one lifecycle rule, is idempotent, exits non-zero when the
read-back disagrees, refuses to run without the SETUP_* credentials, and
names the key-scope cause on AccessDenied. The read-back against the
real bucket — the proof DigitalOcean honors NoncurrentVersionExpiration
with a prefix — is the operator's acceptance walkthrough."""

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app import cli
from app.constants.storage import BACKUP_NONCURRENT_DAYS, BACKUPS_PREFIX

BUCKET = "supercpe-test"


@pytest.fixture
def client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_setup_enables_versioning_and_the_one_rule(client):
    assert cli.run_bucket_setup(client, BUCKET) == 0

    assert client.get_bucket_versioning(Bucket=BUCKET)["Status"] == "Enabled"
    rules = client.get_bucket_lifecycle_configuration(Bucket=BUCKET)["Rules"]
    assert len(rules) == 1
    assert cli.rule_prefix(rules[0]) == BACKUPS_PREFIX
    assert rules[0]["NoncurrentVersionExpiration"]["NoncurrentDays"] == (
        BACKUP_NONCURRENT_DAYS
    )
    # The one rule expires noncurrent backup versions and nothing else:
    # no Expiration action that could touch current 9.02 objects.
    assert "Expiration" not in rules[0]


def test_setup_is_idempotent(client, capsys):
    assert cli.run_bucket_setup(client, BUCKET) == 0
    first = capsys.readouterr().out
    assert cli.run_bucket_setup(client, BUCKET) == 0
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
    assert cli.run_bucket_setup(ReadBackLies(client), BUCKET) == 1
    assert "FAILED" in capsys.readouterr().err


def test_bucket_setup_refuses_without_credentials(monkeypatch, capsys):
    monkeypatch.delenv("SETUP_SPACES_KEY", raising=False)
    monkeypatch.delenv("SETUP_SPACES_SECRET", raising=False)
    assert cli.bucket_setup() == 2
    err = capsys.readouterr().err
    assert "SETUP_SPACES_KEY" in err
    assert "SETUP_SPACES_SECRET" in err


class DeniesBucketConfiguration:
    """A client answering bucket-configuration calls the way the real
    endpoint answers a bucket-scoped key: AccessDenied, even though the
    same key has full object permissions."""

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    def put_bucket_versioning(self, **kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutBucketVersioning",
        )


def test_access_denied_names_the_key_scope_cause(client, capsys):
    """The 2026-08-30 failure: 'temporary Full Access key' read as a
    bucket-scoped key with full object rights, which cannot make
    bucket-configuration calls. The tool must name the cause."""
    assert cli.run_bucket_setup(DeniesBucketConfiguration(client), BUCKET) == 1
    err = capsys.readouterr().err
    assert "bucket-scoped" in err
    assert "All Permissions" in err
