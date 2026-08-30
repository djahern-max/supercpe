"""/api/v1/health (012): reports version, env, database, storage,
ffprobe, and the last backup stamp; 503 the moment any component is
error (4.05.2 — the uptime monitor watches this endpoint)."""

import importlib
import io

from moto import mock_aws

from app.config import settings
from app.constants.storage import (
    BACKUP_LATEST_KEY,
    HEALTH_SENTINEL_KEY,
    OFFSITE_STAMP_KEY,
)
from app.main import app
from app.storage import LocalStorage, SpacesStorage, get_storage


def test_health_reports_every_component_ok(client, storage_root):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == settings.app_version
    assert body["env"] == "dev"
    assert body["database"] == "ok"
    assert body["storage"] == "ok"
    assert body["ffprobe"] == "ok"
    # LocalStorage: nothing to version, so the 013 control reports ok.
    assert body["bucket_versioning"] == "ok"
    assert body["last_backup_at"] is None
    assert body["last_offsite_backup_at"] is None
    # The local check wrote its own sentinel: a writable disk is what
    # storage health means under LocalStorage.
    assert LocalStorage(storage_root).exists(HEALTH_SENTINEL_KEY)


def test_health_reads_last_backup_from_latest(client, storage_root):
    stamp = "2026-08-29T03:15:00+00:00"
    LocalStorage(storage_root).put(
        BACKUP_LATEST_KEY,
        io.BytesIO(f"{stamp}\nbackups/2026-08-29.dump.gz\n".encode()),
    )
    body = client.get("/api/v1/health").json()
    assert body["last_backup_at"] == stamp


class BrokenStorage:
    """A storage whose every call fails, as Spaces does with bad
    credentials or no network."""

    def exists(self, key):
        raise ConnectionError("no route to bucket")

    def open(self, key):
        raise ConnectionError("no route to bucket")


def test_health_is_503_and_names_storage_when_it_fails(client):
    app.dependency_overrides[get_storage] = lambda: BrokenStorage()
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["storage"] == "error"
    assert body["database"] == "ok"


def test_health_reads_last_offsite_backup_from_the_stamp(client, storage_root):
    stamp = "2026-08-30T03:20:00+00:00"
    LocalStorage(storage_root).put(OFFSITE_STAMP_KEY, io.BytesIO(f"{stamp}\n".encode()))
    body = client.get("/api/v1/health").json()
    assert body["last_offsite_backup_at"] == stamp
    # Stale or missing off-site never flips the status code by itself —
    # that alarm belongs to the uptime monitor, like last_backup_at.
    assert client.get("/api/v1/health").status_code == 200


def test_health_is_503_when_bucket_versioning_is_off(client):
    """The /health side of the 013 control: an operator who suspends
    versioning in the control panel goes red at the next probe even
    though the app booted with it Enabled."""
    with mock_aws():
        spaces = SpacesStorage(
            bucket="supercpe-test",
            region="us-east-1",
            endpoint="https://s3.amazonaws.com",
            key="testing",
            secret="testing",
        )
        spaces.client.create_bucket(Bucket="supercpe-test")
        spaces.put(HEALTH_SENTINEL_KEY, io.BytesIO(b"ok"))
        app.dependency_overrides[get_storage] = lambda: spaces

        response = client.get("/api/v1/health")
        assert response.status_code == 503
        body = response.json()
        assert body["bucket_versioning"] == "error"
        assert body["storage"] == "ok"

        spaces.client.put_bucket_versioning(
            Bucket="supercpe-test", VersioningConfiguration={"Status": "Enabled"}
        )
        assert client.get("/api/v1/health").status_code == 200


def test_media_route_is_absent_under_spaces(monkeypatch):
    """main.py mounts /media/ only for the local backend; under Spaces
    the route does not exist at all."""
    import app.main as main_module

    monkeypatch.setattr(settings, "storage_backend", "spaces")
    try:
        reloaded = importlib.reload(main_module)
        paths = [route.path for route in reloaded.app.routes]
        assert not any(path.startswith("/api/v1/media") for path in paths)
    finally:
        monkeypatch.setattr(settings, "storage_backend", "local")
        restored = importlib.reload(main_module)
        assert any(
            route.path.startswith("/api/v1/media") for route in restored.app.routes
        )
