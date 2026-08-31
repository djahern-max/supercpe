"""Feature 020: per-jurisdiction credit policy.

The table ships empty; a fact reaches a participant only when the admin
verified it (increment + source + date), and every miss on the hint
endpoint is the same 404. The board round-down is computed per request
and never touches 005's stored award, and the certificate stays free of
jurisdiction content (9.01 item 10 untouched)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.constants.jurisdiction_policy import (
    CREDIT_INCREMENT_STEPS,
    FINAL_AUTHORITY_SENTENCE,
)
from app.constants.jurisdictions import US_JURISDICTIONS
from app.models.course import Course
from app.services import certificates
from app.services import jurisdictions as jurisdictions_service
from app.services import sponsor as sponsor_service
from app.services.jurisdictions import JurisdictionRuleViolation
from tests.conftest import login, make_account
from tests.test_certificates import pdf_text
from tests.test_completion import complete_profile, make_completed
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    make_participant,
    make_published_course,
)

TODAY = date.today()


def fill_nh(db, increment="one_fifth", **overrides):
    fields = {
        "non_technical_cap_note": "",
        "source": "https://www.oplc.nh.gov/accountancy",
        "verified_on": TODAY,
        "notes": "",
    }
    fields.update(overrides)
    return jurisdictions_service.upsert(db, "NH", increment, **fields)


def participant_with_state(db, state="NH"):
    participant = make_participant(db)
    participant.state = state
    db.commit()
    return participant


def login_participant(client):
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)


NOTE_URL = "/api/v1/courses/GOLD/jurisdiction-note"


# --- the rounding helper -----------------------------------------------------


def test_round_down_examples_from_7_01_1():
    # 7.01.1: 1.4 is 1.0 under one-half increments; 140 minutes is 2.8
    # under one-fifth and 2.5 under one-half.
    assert jurisdictions_service.board_rounded(
        Decimal("1.4"), "one_half"
    ) == Decimal("1.0")
    assert jurisdictions_service.board_rounded(
        Decimal("2.8"), "one_half"
    ) == Decimal("2.5")
    assert jurisdictions_service.board_rounded(
        Decimal("2.8"), "whole"
    ) == Decimal("2.0")
    # One-fifth boards need nothing computed: the stored award already is
    # in one-fifth increments.
    assert jurisdictions_service.board_rounded(Decimal("1.4"), "one_fifth") is None
    assert jurisdictions_service.board_rounded(Decimal("1.4"), "unknown") is None


@pytest.mark.parametrize("increment", ["one_half", "whole"])
def test_round_down_never_rounds_up_across_the_range(increment):
    """Property sweep: every stored one-fifth award from 0.0 to 10.0."""
    step = CREDIT_INCREMENT_STEPS[increment]
    for fifths in range(0, 51):
        raw = Decimal(fifths) * Decimal("0.2")
        rounded = jurisdictions_service.board_rounded(raw, increment)
        assert rounded <= raw
        assert rounded % step == 0
        assert raw - rounded < step


# --- displayability ----------------------------------------------------------


def test_fresh_database_shows_no_hint_anywhere(client, db_session):
    make_published_course(db_session)
    participant_with_state(db_session)
    login_participant(client)
    assert client.get(NOTE_URL).status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"increment": "unknown"},
        {"source": ""},
        {"source": "   "},
        {"verified_on": None},
    ],
)
def test_incomplete_row_is_not_displayable(client, db_session, overrides):
    make_published_course(db_session)
    participant_with_state(db_session)
    increment = overrides.pop("increment", "one_fifth")
    fill_nh(db_session, increment, **overrides)
    login_participant(client)
    assert client.get(NOTE_URL).status_code == 404


def test_complete_row_shows_the_hint(client, db_session):
    course, _ = make_published_course(db_session)
    participant_with_state(db_session)
    fill_nh(db_session)
    login_participant(client)
    response = client.get(NOTE_URL)
    assert response.status_code == 200
    assert response.json() == {
        "jurisdiction": "NH",
        "jurisdiction_name": "New Hampshire",
        "credit_increment": "one_fifth",
        # The 005 stored award, unchanged (GOLD's golden 0.4).
        "recommended_credit": "0.4",
        "board_rounded_credit": None,
        "non_technical_cap_note": None,
        "verified_on": TODAY.isoformat(),
        "final_authority": FINAL_AUTHORITY_SENTENCE,
    }


# --- who gets a hint ---------------------------------------------------------


def test_participant_without_a_state_gets_404(client, db_session):
    make_published_course(db_session)
    make_participant(db_session)
    fill_nh(db_session)
    login_participant(client)
    assert client.get(NOTE_URL).status_code == 404


def test_anonymous_gets_404_in_both_site_modes(client, db_session):
    make_published_course(db_session)
    fill_nh(db_session)
    # coming_soon: the site gate answers.
    assert client.get(NOTE_URL).status_code == 404
    # open: the endpoint itself answers — a hint is per-viewer.
    complete_profile(db_session)
    sponsor_service.get_profile(db_session).site_mode = "open"
    db_session.commit()
    assert client.get(NOTE_URL).status_code == 404


def test_non_participant_session_gets_404(client, db_session, admin_headers):
    make_published_course(db_session)
    fill_nh(db_session)
    assert client.get(NOTE_URL).status_code == 404


def test_unpublished_course_gets_404(client, db_session):
    from tests.test_enrollments import make_publish_ready_course

    make_publish_ready_course(db_session)
    participant_with_state(db_session)
    fill_nh(db_session)
    login_participant(client)
    assert client.get(NOTE_URL).status_code == 404


def test_unknown_field_of_study_gets_no_hint(client, db_session):
    course, _ = make_published_course(db_session)
    participant_with_state(db_session)
    fill_nh(db_session)
    course.field_of_study = "Alchemy"
    db_session.commit()
    login_participant(client)
    assert client.get(NOTE_URL).status_code == 404


# --- the computed round-down -------------------------------------------------


def test_coarser_board_shows_the_round_down_and_never_the_stored_value(
    client, db_session
):
    course, _ = make_published_course(db_session)
    participant_with_state(db_session)
    fill_nh(db_session, "one_half")
    # A stored award the 7.01.1 example uses; set directly so the round
    # trip is visible (1.4 under one-half -> 1.0).
    course.credit_award = Decimal("1.4")
    db_session.commit()
    login_participant(client)

    body = client.get(NOTE_URL).json()
    assert body["credit_increment"] == "one_half"
    assert body["recommended_credit"] == "1.4"
    assert body["board_rounded_credit"] == "1.0"

    # The computation never alters 005's stored value.
    db_session.expire_all()
    stored = db_session.get(Course, course.id)
    assert stored.credit_award == Decimal("1.4")

    fill_nh(db_session, "whole")
    assert client.get(NOTE_URL).json()["board_rounded_credit"] == "1.0"
    db_session.expire_all()
    assert db_session.get(Course, course.id).credit_award == Decimal("1.4")


# --- the cap note ------------------------------------------------------------


def test_cap_note_appears_only_for_non_technical_fields(client, db_session):
    course, _ = make_published_course(db_session)
    participant_with_state(db_session)
    fill_nh(
        db_session,
        non_technical_cap_note=(
            "No more than half of total hours may be non-technical."
        ),
    )
    login_participant(client)

    # GOLD's field is Accounting — technical per the 2024 document: the
    # cap is somebody else's problem and never shows.
    assert client.get(NOTE_URL).json()["non_technical_cap_note"] is None

    course.field_of_study = "Personal Development"
    db_session.commit()
    body = client.get(NOTE_URL).json()
    assert (
        body["non_technical_cap_note"]
        == "No more than half of total hours may be non-technical."
    )


# --- the participant's state -------------------------------------------------


STATE_URL = "/api/v1/auth/me/state"


def test_participant_sets_changes_and_clears_their_state(client, db_session):
    make_participant(db_session)
    login_participant(client)

    assert client.get(STATE_URL).json() == {"state": None}
    assert client.put(STATE_URL, json={"state": "nh"}).json() == {
        "state": "NH"
    }
    assert client.put(STATE_URL, json={"state": "VT"}).json() == {
        "state": "VT"
    }
    assert client.put(STATE_URL, json={"state": None}).json() == {
        "state": None
    }

    bad = client.put(STATE_URL, json={"state": "ZZ"})
    assert bad.status_code == 422
    assert "ZZ" in bad.json()["errors"][0]


def test_state_routes_are_participant_only(client, db_session, admin_headers):
    assert client.get(STATE_URL).status_code == 403
    assert client.put(STATE_URL, json={"state": "NH"}).status_code == 403


# --- admin -------------------------------------------------------------------


ADMIN_URL = "/api/v1/admin/jurisdictions"


def test_admin_list_serves_all_55_codes_empty(client, db_session, admin_headers):
    rows = client.get(ADMIN_URL).json()
    assert len(rows) == 55
    assert [row["jurisdiction"] for row in rows] == list(US_JURISDICTIONS)
    assert all(row["credit_increment"] == "unknown" for row in rows)
    assert all(row["displayable"] is False for row in rows)
    assert all(row["verification_stale"] is False for row in rows)


def test_admin_upsert_creates_on_edit_and_derives_displayable(
    client, db_session, admin_headers
):
    response = client.put(
        f"{ADMIN_URL}/NH",
        json={
            "credit_increment": "one_fifth",
            "source": "board site",
            "verified_on": TODAY.isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["displayable"] is True
    assert body["name"] == "New Hampshire"

    rows = client.get(ADMIN_URL).json()
    assert sum(1 for row in rows if row["displayable"]) == 1

    # Losing the source loses displayability; the row remains.
    downgraded = client.put(
        f"{ADMIN_URL}/NH",
        json={
            "credit_increment": "one_fifth",
            "verified_on": TODAY.isoformat(),
        },
    ).json()
    assert downgraded["displayable"] is False


def test_admin_upsert_refuses_junk(client, db_session, admin_headers):
    assert (
        client.put(
            f"{ADMIN_URL}/XX", json={"credit_increment": "one_fifth"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{ADMIN_URL}/NH", json={"credit_increment": "one_third"}
        ).status_code
        == 422
    )
    future = (TODAY + timedelta(days=2)).isoformat()
    assert (
        client.put(
            f"{ADMIN_URL}/NH",
            json={"credit_increment": "one_fifth", "verified_on": future},
        ).status_code
        == 422
    )


def test_verification_staleness_nudges_after_a_year(
    client, db_session, admin_headers
):
    fill_nh(db_session, verified_on=TODAY - timedelta(days=400))
    row = next(
        r for r in client.get(ADMIN_URL).json() if r["jurisdiction"] == "NH"
    )
    assert row["verification_stale"] is True
    assert row["displayable"] is True


def test_upsert_validates_before_writing(db_session):
    with pytest.raises(JurisdictionRuleViolation):
        jurisdictions_service.upsert(
            db_session, "XX", "one_fifth", "", "src", TODAY, ""
        )
    assert jurisdictions_service.all_rows(db_session) == {}


# --- the certificate stays jurisdiction-free ---------------------------------


def test_certificate_render_pinned_free_of_jurisdiction_content(db_session):
    """9.01 item 10 and the credit line are untouched by 020: even for a
    participant with a state and a displayable coarser-increment row, the
    certificate prints the 005 award and no board content."""
    fill_nh(db_session, "one_half")
    course, enrollment, _ = make_completed(db_session)
    participant = enrollment.account
    participant.state = "NH"
    db_session.commit()

    text = pdf_text(
        certificates.render(enrollment.completion.certificate_snapshot)
    )
    assert "0.4 in Accounting" in text
    assert "CPE credits have been granted based on a 50-minute hour." in text
    for word in ("jurisdiction", "increment", "board"):
        assert word not in text.lower()
    assert "New Hampshire" not in text
    assert "jurisdiction" not in str(
        enrollment.completion.certificate_snapshot
    )
