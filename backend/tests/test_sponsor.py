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
