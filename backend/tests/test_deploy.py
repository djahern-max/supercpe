"""deploy/wait-for-health.sh (023c D4): the deploy's health wait tells
three outcomes apart — new version healthy, new version running but
unhealthy, and sha never reported (old version may still be running). A
fake `curl` on PATH stands in for the endpoint."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy"
WAIT_SCRIPT = DEPLOY_DIR / "wait-for-health.sh"

FAKE_CURL = """#!/usr/bin/env bash
# Stands in for curl: writes $FAKE_BODY to the -o file, prints $FAKE_STATUS
# as the -w '%{http_code}' output. Counts calls in $FAKE_CALLS.
while [ $# -gt 0 ]; do
    case "$1" in -o) OUT="$2"; shift ;; esac
    shift
done
printf '%s' "$FAKE_BODY" > "$OUT"
printf '%s' "$FAKE_STATUS"
echo x >> "$FAKE_CALLS"
"""


@pytest.fixture
def fake_curl(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CALLS", str(calls))
    return calls


def wait(sha, status, body, attempts=3):
    return subprocess.run(
        ["bash", str(WAIT_SCRIPT), sha, "http://health.test", str(attempts), "0"],
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_STATUS": str(status), "FAKE_BODY": body},
    )


def test_new_version_healthy_exits_zero(fake_curl):
    result = wait("abc123", 200, '{"version":"abc123","storage":"ok"}')
    assert result.returncode == 0, result.stderr
    assert "Deployed abc123" in result.stdout
    # Done on the first healthy answer, not after the whole window.
    assert fake_curl.read_text().count("x") == 1


def test_new_version_unhealthy_names_the_failing_components(fake_curl):
    body = (
        '{"version":"abc123","env":"prod","database":"ok","storage":"error",'
        '"ffprobe":"ok","bucket_versioning":"error","last_backup_at":null}'
    )
    result = wait("abc123", 503, body)
    assert result.returncode == 1
    assert "New version abc123 running, unhealthy" in result.stderr
    assert "storage bucket_versioning" in result.stderr
    assert "old version" not in result.stderr
    # It kept polling: a component can still be coming up.
    assert fake_curl.read_text().count("x") == 3


def test_sha_never_reported_says_the_old_version_may_be_running(fake_curl):
    result = wait("abc123", 200, '{"version":"old000","storage":"ok"}')
    assert result.returncode == 2
    assert "Health never reported abc123" in result.stderr
    assert "the old version may still be running" in result.stderr
    assert "unhealthy" not in result.stderr


def test_a_dead_endpoint_is_the_old_version_outcome(fake_curl):
    """No body at all (Caddy not up yet, connection refused) is not a
    new-version signal."""
    result = wait("abc123", "000", "")
    assert result.returncode == 2
    assert "Health never reported abc123" in result.stderr


def test_deploy_script_hands_the_wait_to_the_shared_loop():
    script = (DEPLOY_DIR / "deploy.sh").read_text()
    assert "wait-for-health.sh" in script
    # The old inline loop, which treated any non-2xx as "old version", is
    # gone.
    assert "Health never reported" not in script
    assert os.access(WAIT_SCRIPT, os.X_OK)
