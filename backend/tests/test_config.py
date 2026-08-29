"""Boot refusals (012): every production misconfiguration is named, all
at once, in the 002 style — fail at boot, not at first request."""

import pytest

from app.config import (
    ConfigurationError,
    Settings,
    boot_violations,
    ensure_boot_config,
)

SPACES_OK = dict(
    spaces_bucket="supercpe",
    spaces_region="nyc3",
    spaces_endpoint="https://nyc3.digitaloceanspaces.com",
    spaces_key="DO00EXAMPLEKEY",
    spaces_secret="s" * 43,
)

PROD_OK = dict(
    database_url="postgresql+psycopg://u:p@host:25060/supercpe?sslmode=require",
    cors_origins="https://supercpe.com",
    dev=False,
    env="prod",
    storage_backend="spaces",
    **SPACES_OK,
)


def make_settings(**overrides):
    values = dict(database_url="postgresql+psycopg://u:p@localhost/supercpe")
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_dev_defaults_have_no_violations():
    assert boot_violations(make_settings()) == []


def test_a_correct_prod_config_has_no_violations():
    assert boot_violations(make_settings(**PROD_OK)) == []


@pytest.mark.parametrize(
    "override, named",
    [
        (dict(dev=True), "DEV"),
        (dict(cors_origins="https://supercpe.com,http://localhost:5173"), "CORS_ORIGINS"),
        (
            dict(database_url="postgresql+psycopg://u:p@host:25060/supercpe"),
            "sslmode=require",
        ),
        (dict(storage_backend="local"), "STORAGE_BACKEND"),
        (dict(spaces_secret="short"), "SPACES_SECRET"),
    ],
)
def test_each_prod_refusal_names_its_variable(override, named):
    values = dict(PROD_OK)
    values.update(override)
    violations = boot_violations(make_settings(**values))
    assert violations, f"expected a violation for {named}"
    assert any(named in violation for violation in violations)


@pytest.mark.parametrize(
    "missing",
    ["spaces_bucket", "spaces_region", "spaces_endpoint", "spaces_key", "spaces_secret"],
)
def test_spaces_backend_requires_every_spaces_var(missing):
    values = dict(storage_backend="spaces", **SPACES_OK)
    values[missing] = ""
    violations = boot_violations(make_settings(**values))
    assert any(missing.upper() in violation for violation in violations)


def test_unknown_env_and_backend_are_refused():
    violations = boot_violations(
        make_settings(env="staging", storage_backend="ftp")
    )
    assert any("ENV" in violation for violation in violations)
    assert any("STORAGE_BACKEND" in violation for violation in violations)


def test_ensure_boot_config_lists_every_violation_at_once():
    values = dict(PROD_OK)
    values.update(dev=True, cors_origins="*", storage_backend="local")
    with pytest.raises(ConfigurationError) as excinfo:
        ensure_boot_config(make_settings(**values))
    message = str(excinfo.value)
    for named in ("DEV", "CORS_ORIGINS", "STORAGE_BACKEND"):
        assert named in message
