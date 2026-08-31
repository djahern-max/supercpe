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


OFFSITE_OK = dict(
    offsite_endpoint="https://s3.us-west-004.backblazeb2.com",
    offsite_region="us-west-004",
    offsite_bucket="supercpe-offsite",
    offsite_key="004example0000000000000",
    offsite_secret="o" * 43,
)


def test_prod_with_full_offsite_config_has_no_violations():
    assert boot_violations(make_settings(**PROD_OK, **OFFSITE_OK)) == []


def test_prod_without_offsite_boots():
    """The missing-offsite state is reported by /health, not refused at
    boot, so the site stays up while a provider is chosen or replaced."""
    assert boot_violations(make_settings(**PROD_OK)) == []


@pytest.mark.parametrize(
    "missing",
    [
        "offsite_endpoint",
        "offsite_region",
        "offsite_bucket",
        "offsite_key",
        "offsite_secret",
    ],
)
def test_offsite_config_is_all_or_nothing(missing):
    # In dev too: a partial OFFSITE_* is a typo, never a valid state.
    values = dict(OFFSITE_OK)
    values[missing] = ""
    violations = boot_violations(make_settings(**values))
    assert len(violations) == 1
    assert missing.upper() in violations[0]


def test_prod_offsite_endpoint_at_digitalocean_is_refused():
    values = dict(PROD_OK, **OFFSITE_OK)
    values["offsite_endpoint"] = "https://sfo3.digitaloceanspaces.com"
    violations = boot_violations(make_settings(**values))
    assert any("OFFSITE_ENDPOINT" in violation for violation in violations)


def test_offsite_endpoint_at_digitalocean_is_allowed_in_dev():
    values = dict(OFFSITE_OK)
    values["offsite_endpoint"] = "https://sfo3.digitaloceanspaces.com"
    assert boot_violations(make_settings(**values)) == []


def test_prod_offsite_secret_follows_the_length_rule():
    values = dict(PROD_OK, **OFFSITE_OK)
    values["offsite_secret"] = "short"
    violations = boot_violations(make_settings(**values))
    assert any("OFFSITE_SECRET" in violation for violation in violations)


EMAIL_OK = dict(
    email_backend="smtp",
    email_host="smtp.example.com",
    email_port=587,
    email_username="mailer",
    email_password="e" * 20,
    email_from="superCPE <no-reply@supercpe.com>",
)


def test_prod_with_smtp_email_has_no_violations():
    assert boot_violations(make_settings(**PROD_OK, **EMAIL_OK)) == []


def test_email_absent_entirely_is_valid_config():
    """The site can boot — and run coming-soon — with no email settings
    at all; the coming_soon -> open flip is what refuses (017), not boot."""
    assert boot_violations(make_settings()) == []
    assert boot_violations(make_settings(**PROD_OK)) == []


@pytest.mark.parametrize(
    "missing, unset",
    [
        ("email_host", ""),
        ("email_port", 0),
        ("email_username", ""),
        ("email_password", ""),
        ("email_from", ""),
    ],
)
def test_email_config_is_all_or_nothing(missing, unset):
    # In dev and with the console backend too: a partial EMAIL_* is a
    # typo, never a valid state.
    values = dict(EMAIL_OK, email_backend="console")
    values[missing] = unset
    violations = boot_violations(make_settings(**values))
    assert len(violations) == 1
    assert missing.upper() in violations[0]


def test_smtp_backend_with_nothing_set_names_all_five():
    violations = boot_violations(make_settings(email_backend="smtp"))
    for var in ("EMAIL_HOST", "EMAIL_PORT", "EMAIL_USERNAME", "EMAIL_PASSWORD", "EMAIL_FROM"):
        assert any(var in violation for violation in violations)


def test_unknown_email_backend_is_refused():
    violations = boot_violations(make_settings(email_backend="carrier-pigeon"))
    assert any("EMAIL_BACKEND" in violation for violation in violations)


@pytest.mark.parametrize(
    "email_from, ok",
    [
        ("no-reply@supercpe.com", True),
        ("superCPE <no-reply@supercpe.com>", True),
        ("not-an-address", False),
        ("@supercpe.com", False),
    ],
)
def test_email_from_must_parse_as_an_address(email_from, ok):
    values = dict(EMAIL_OK, email_from=email_from)
    violations = boot_violations(make_settings(**values))
    if ok:
        assert violations == []
    else:
        assert any("EMAIL_FROM" in violation for violation in violations)


def test_ensure_boot_config_lists_every_violation_at_once():
    values = dict(PROD_OK)
    values.update(dev=True, cors_origins="*", storage_backend="local")
    with pytest.raises(ConfigurationError) as excinfo:
        ensure_boot_config(make_settings(**values))
    message = str(excinfo.value)
    for named in ("DEV", "CORS_ORIGINS", "STORAGE_BACKEND"):
        assert named in message
