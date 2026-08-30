"""`python -m app.cli preflight` (014a): every boot refusal, run
without booting, so deploy.sh can turn a would-be outage into a failed
deploy with the old version still serving. The checks are the same code
paths the lifespan uses — boot_violations and ensure_bucket_versioning —
never a duplicate of the rules."""

import pytest
from moto import mock_aws

import app.storage
from app import cli
from app.config import settings
from app.storage import SpacesStorage

BUCKET = "supercpe-test"

PROD_OK = dict(
    database_url="postgresql+psycopg://u:p@host:25060/supercpe?sslmode=require",
    cors_origins="https://supercpe.com",
    dev=False,
    env="prod",
    storage_backend="spaces",
    spaces_bucket=BUCKET,
    spaces_region="us-east-1",
    spaces_endpoint="https://s3.amazonaws.com",
    spaces_key="DO00EXAMPLEKEY",
    spaces_secret="s" * 43,
)


@pytest.fixture
def prod_settings(monkeypatch):
    for name, value in PROD_OK.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def spaces(monkeypatch):
    """A moto bucket wired in as the cached storage get_storage returns,
    the way the CLI process would build it from the same settings."""
    with mock_aws():
        storage = SpacesStorage(
            bucket=BUCKET,
            region="us-east-1",
            endpoint="https://s3.amazonaws.com",
            key="testing",
            secret="testing",
        )
        storage.client.create_bucket(Bucket=BUCKET)
        monkeypatch.setattr(app.storage, "_spaces", storage)
        yield storage


def enable_versioning(spaces):
    spaces.client.put_bucket_versioning(
        Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"}
    )


def test_preflight_passes_a_bootable_prod_config(prod_settings, spaces, capsys):
    enable_versioning(spaces)
    assert cli.preflight() == 0
    assert "preflight ok" in capsys.readouterr().out


def test_preflight_fails_when_versioning_is_off(prod_settings, spaces, capsys):
    assert cli.preflight() == 1
    assert "versioning" in capsys.readouterr().err


def test_preflight_fails_when_the_bucket_is_unreachable(
    prod_settings, spaces, monkeypatch, capsys
):
    """Acceptance 4's negative gate: a bucket that does not exist (or a
    versioning read that fails outright) is a refusal with the check
    named, not a crash and not a pass."""
    monkeypatch.setattr(settings, "spaces_bucket", "no-such-bucket")
    monkeypatch.setattr(spaces, "bucket", "no-such-bucket")
    assert cli.preflight() == 1
    assert "bucket_versioning" in capsys.readouterr().err


def test_preflight_lists_config_violations(
    prod_settings, spaces, monkeypatch, capsys
):
    enable_versioning(spaces)
    # Same code path as boot_violations: every violation, all at once.
    monkeypatch.setattr(settings, "dev", True)
    monkeypatch.setattr(settings, "cors_origins", "*")
    assert cli.preflight() == 1
    err = capsys.readouterr().err
    assert "DEV" in err
    assert "CORS_ORIGINS" in err


def test_preflight_skips_the_bucket_check_under_local_storage(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "local")
    assert cli.preflight() == 0


def test_deploy_script_runs_preflight_before_migrations():
    """deploy.sh must gate on preflight before the schema moves and
    before the running containers are touched (rollback.sh execs
    deploy.sh, so it inherits the same gate)."""
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[2] / "deploy" / "deploy.sh"
    ).read_text()
    preflight_at = script.index("python -m app.cli preflight")
    migrate_at = script.index("alembic upgrade head")
    assert preflight_at < migrate_at
