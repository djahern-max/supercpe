import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.sponsor import SponsorProfile
from app.services.sponsor import get_profile


def full_profile(**overrides):
    data = {
        "name": "SuperCPE",
        "legal_name": "SuperCPE LLC",
        "registry_status": "not_registered",
        "national_registry_id": "",
        "website": "https://supercpe.com",
        "contact_email": "admin@supercpe.com",
        "contact_phone": "",
        "address": "",
        "other_certificate_statements": "",
    }
    data.update(overrides)
    return data


def test_fresh_database_has_one_profile_with_all_three_missing(client, admin_headers, db_session):
    response = client.get("/api/v1/admin/sponsor", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["missing_fields"]) == [
        "name",
        "national_registry_id",
        "registry_status",
    ]
    assert body["may_claim_registry"] is False

    rows = db_session.execute(select(SponsorProfile)).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == 1


def test_missing_fields_on_blank_profile_does_not_raise(db_session):
    profile = get_profile(db_session)
    assert profile.missing_fields() == [
        "name",
        "national_registry_id",
        "registry_status",
    ]


def test_put_shrinks_missing_fields(client, admin_headers):
    response = client.put(
        "/api/v1/admin/sponsor", headers=admin_headers, json=full_profile()
    )
    assert response.status_code == 200
    assert response.json()["missing_fields"] == ["national_registry_id", "registry_status"]

    response = client.put(
        "/api/v1/admin/sponsor",
        headers=admin_headers,
        json=full_profile(registry_status="registered", national_registry_id="112233"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["missing_fields"] == []
    assert body["may_claim_registry"] is True


def test_registered_with_blank_id_is_refused(client, admin_headers):
    response = client.put(
        "/api/v1/admin/sponsor",
        headers=admin_headers,
        json=full_profile(registry_status="registered", national_registry_id=""),
    )
    assert response.status_code == 422
    assert "blank" in response.json()["errors"][0]


def test_not_registered_with_id_is_refused(client, admin_headers):
    response = client.put(
        "/api/v1/admin/sponsor",
        headers=admin_headers,
        json=full_profile(registry_status="not_registered", national_registry_id="112233"),
    )
    assert response.status_code == 422
    assert "may not claim" in response.json()["errors"][0]


def test_public_endpoint_omits_registry_id_when_not_registered(client, admin_headers):
    client.put("/api/v1/admin/sponsor", headers=admin_headers, json=full_profile())
    response = client.get("/api/v1/sponsor")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SuperCPE"
    assert "national_registry_id" not in body


def test_public_endpoint_includes_registry_id_when_registered(client, admin_headers):
    client.put(
        "/api/v1/admin/sponsor",
        headers=admin_headers,
        json=full_profile(registry_status="registered", national_registry_id="112233"),
    )
    response = client.get("/api/v1/sponsor")
    assert response.status_code == 200
    assert response.json()["national_registry_id"] == "112233"

    # Toggling back off the Registry hides the ID again.
    client.put("/api/v1/admin/sponsor", headers=admin_headers, json=full_profile())
    assert "national_registry_id" not in client.get("/api/v1/sponsor").json()


def test_public_endpoint_carries_contact_email(client, admin_headers):
    """027: the site footer and the exhausted re-takes notice render the
    sponsor's contact address from this payload; it must be here, and
    nothing else new may ride along with it."""
    client.put("/api/v1/admin/sponsor", headers=admin_headers, json=full_profile())
    body = client.get("/api/v1/sponsor").json()
    assert body["contact_email"] == full_profile()["contact_email"]
    assert set(body) == {"name", "website", "contact_email"}


def test_state_registrations_replace_as_a_set(client, admin_headers):
    put = lambda rows: client.put(
        "/api/v1/admin/sponsor/state-registrations", headers=admin_headers, json=rows
    )
    response = put(
        [
            {"state": "NH", "registration_number": "1234"},
            {"state": "NY", "registration_number": "5678", "notes": "expires 2027"},
        ]
    )
    assert response.status_code == 200
    assert [row["state"] for row in response.json()] == ["NH", "NY"]

    response = put([{"state": "NH", "registration_number": "1234"}])
    assert response.status_code == 200
    assert [row["state"] for row in response.json()] == ["NH"]

    listed = client.get("/api/v1/admin/sponsor", headers=admin_headers).json()
    assert [row["state"] for row in listed["state_registrations"]] == ["NH"]


def test_lowercase_state_code_is_uppercased(client, admin_headers):
    response = client.put(
        "/api/v1/admin/sponsor/state-registrations",
        headers=admin_headers,
        json=[{"state": "nh", "registration_number": "1234"}],
    )
    assert response.status_code == 200
    assert response.json()[0]["state"] == "NH"


def test_duplicate_state_in_one_payload_is_refused(client, admin_headers):
    response = client.put(
        "/api/v1/admin/sponsor/state-registrations",
        headers=admin_headers,
        json=[
            {"state": "NH", "registration_number": "1234"},
            {"state": "nh", "registration_number": "9999"},
        ],
    )
    assert response.status_code == 422
    assert "Duplicate state" in response.json()["errors"][0]


def test_second_profile_row_cannot_be_inserted(db_session):
    get_profile(db_session)
    db_session.add(SponsorProfile(id=2))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_admin_endpoints_require_token(client):
    assert client.get("/api/v1/admin/sponsor").status_code == 401
    assert client.put("/api/v1/admin/sponsor", json=full_profile()).status_code == 401


# --- 032: the certificate mark -----------------------------------------------


LOGO_URL = "/api/v1/admin/sponsor/logo"


def png_bytes(width=40, height=20) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", (width, height), "#1f4e8c").save(buffer, "PNG")
    return buffer.getvalue()


def test_logo_upload_png_then_clear(client, admin_headers, db_session, storage_root):
    assert client.get("/api/v1/admin/sponsor", headers=admin_headers).json()[
        "logo_path"
    ] is None
    response = client.put(
        LOGO_URL,
        headers=admin_headers,
        files={"file": ("anything.bin", png_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["logo_path"] == "sponsor/logo.png"
    assert (storage_root / "sponsor" / "logo.png").read_bytes() == png_bytes()
    assert get_profile(db_session).logo_path == "sponsor/logo.png"

    cleared = client.delete(LOGO_URL, headers=admin_headers)
    assert cleared.status_code == 200
    assert cleared.json()["logo_path"] is None
    db_session.refresh(get_profile(db_session))
    assert get_profile(db_session).logo_path is None
    # Nothing at the storage boundary deletes; the object is simply unused.
    assert (storage_root / "sponsor" / "logo.png").exists()


def test_logo_upload_svg(client, admin_headers, storage_root):
    svg = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    response = client.put(
        LOGO_URL,
        headers=admin_headers,
        files={"file": ("logo.svg", svg, "image/svg+xml")},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["logo_path"] == "sponsor/logo.svg"
    assert (storage_root / "sponsor" / "logo.svg").read_bytes() == svg


def test_logo_refuses_anything_but_png_or_svg(client, admin_headers, db_session):
    for name, content, declared in (
        ("photo.jpg", b"\xff\xd8\xff\xe0" + b"0" * 100, "image/jpeg"),
        ("logo.png", b"not really a png", "image/png"),
        ("notes.txt", b"<html>not svg</html>", "image/svg+xml"),
    ):
        response = client.put(
            LOGO_URL, headers=admin_headers, files={"file": (name, content, declared)}
        )
        assert response.status_code == 422, name
        assert "PNG or an SVG" in response.json()["errors"][0]
    assert get_profile(db_session).logo_path is None


def test_logo_refuses_an_oversize_file(client, admin_headers):
    from app.constants.certificate import LOGO_MAX_BYTES

    content = b"\x89PNG\r\n\x1a\n" + b"0" * LOGO_MAX_BYTES
    response = client.put(
        LOGO_URL, headers=admin_headers, files={"file": ("big.png", content, "image/png")}
    )
    assert response.status_code == 422
    assert "MB or smaller" in response.json()["errors"][0]
