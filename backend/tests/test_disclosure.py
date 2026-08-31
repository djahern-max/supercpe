"""Feature 016: 8.01 disclosure completeness — the named check, the
publish gate on it, the final public payload shape, and the extended
site-open gate.

The compliance-shaped tests are the detail key-set assertion (the exact
inverse of 015's landing payload test: a named field for every applicable
8.01 item) and the Registry-absence walk over both public payloads."""

from app.services import courses as courses_service
from app.services import disclosure
from app.services import sponsor as sponsor_service
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    login,
    publish_test_policies,
)
from tests.test_enrollments import (
    make_publish_ready_course,
    make_published_course,
    make_recorder,
)

PUBLIC_URL = "/api/v1/courses"
SITE_MODE_URL = "/api/v1/admin/site-mode"


def numbers(db, course):
    return [item.number for item in disclosure.missing_items(db, course)]


def make_disclosable_course(db, course_code="GOLD"):
    """A draft course whose every applicable 8.01 item is disclosable:
    `make_publish_ready_course` plus the three policies."""
    course, package = make_publish_ready_course(db, course_code)
    publish_test_policies(db, make_recorder(db))
    return course, package


def claim_registry(db, name="SuperCPE LLC"):
    profile = sponsor_service.get_profile(db)
    profile.name = name
    profile.registry_status = "registered"
    profile.national_registry_id = "112233"
    db.commit()


# --- the completeness check, item by item ------------------------------------


def test_complete_course_has_nothing_missing(db_session):
    course, _ = make_disclosable_course(db_session)
    assert disclosure.missing_items(db_session, course) == []


def test_item_3_fails_when_the_stored_credit_is_stale(db_session):
    course, _ = make_disclosable_course(db_session)
    # The dev-only path around published immutability: touch directly.
    courses_service.touch(course)
    db_session.commit()
    [item] = disclosure.missing_items(db_session, course)
    assert item.number == 3
    assert "unusable" in item.reason


def test_item_3_fails_without_a_field_of_study(db_session):
    course, _ = make_disclosable_course(db_session)
    course.field_of_study = None
    db_session.commit()
    [item] = disclosure.missing_items(db_session, course)
    assert item.number == 3
    assert "field of study" in item.reason


def test_items_4_to_7_fail_when_blank_not_when_none_is_stated(db_session):
    course, _ = make_disclosable_course(db_session)
    # "None" is a stored statement (8.01.2/3.02.1) and satisfies the item;
    # the factory package states it for both 4 and 6.
    assert course.prerequisites == "None"
    assert course.advance_preparation == "None"
    course.prerequisites = "   "
    course.knowledge_level = None
    course.advance_preparation = ""
    course.description = ""
    db_session.commit()
    assert numbers(db_session, course) == [4, 5, 6, 7]


def test_item_1_fails_with_no_objectives_at_all(db_session):
    from tests.test_credit import make_course_row

    course = make_course_row(db_session, "EMPTY")
    assert 1 in numbers(db_session, course)


def test_items_8_to_10_follow_the_published_policies(db_session):
    from app.services import policies as policies_service

    course, _ = make_publish_ready_course(db_session)
    assert numbers(db_session, course) == [8, 9, 10]
    policies_service.publish(
        db_session, "refund", "Refunds.", None, make_recorder(db_session)
    )
    assert numbers(db_session, course) == [8, 10]


def test_item_11_is_not_counted_in_either_registry_state(db_session):
    course, _ = make_disclosable_course(db_session)
    assert disclosure.missing_items(db_session, course) == []
    # Once claimable the statement is a gated constant — still nothing to
    # miss.
    claim_registry(db_session)
    assert disclosure.missing_items(db_session, course) == []


# --- the publish gate ---------------------------------------------------------


def test_publish_refuses_naming_each_missing_item_number(
    client, db_session, admin_headers
):
    course, _ = make_publish_ready_course(db_session)
    response = client.post(f"/api/v1/admin/courses/{course.course_code}/publish")
    assert response.status_code == 422
    errors = response.json()["errors"]
    for number in (8, 9, 10):
        assert any(f"8.01 item {number}" in e for e in errors), errors


def test_a_single_missing_item_blocks_publish_and_restoring_it_publishes(
    client, db_session, admin_headers
):
    course, _ = make_disclosable_course(db_session)
    course.prerequisites = ""
    db_session.commit()
    refused = client.post(f"/api/v1/admin/courses/{course.course_code}/publish")
    assert refused.status_code == 422
    assert any("8.01 item 4" in e for e in refused.json()["errors"])

    course.prerequisites = "None"
    db_session.commit()
    published = client.post(
        f"/api/v1/admin/courses/{course.course_code}/publish"
    )
    assert published.status_code == 200, published.json()


# --- the public payloads ------------------------------------------------------

# Every applicable 8.01 item has a named field (may_claim_registry false,
# so item 11 is inapplicable and absent):
#   1 objectives/outline; 2 program_type; 3 recommended_credit,
#   credit_basis, field_of_study; 4 prerequisites; 5 knowledge_level;
#   6 advance_preparation; 7 description; 8 registration_policy;
#   9 refund_policy; 10 complaint_policy — plus the identity, length, and
#   4.01 provenance fields.
EXPECTED_DETAIL_KEYS = {
    "course_code",
    "title",
    "description",
    "program_type",
    "field_of_study",
    "knowledge_level",
    "prerequisites",
    "advance_preparation",
    "lesson_count",
    "total_duration_seconds",
    # 018: the price, a commercial fact beside the 8.01 items.
    "price_cents",
    "recommended_credit",
    "credit_basis",
    "developed_by",
    "reviewed_by",
    "last_reviewed",
    "last_documented_date",
    "objectives",
    "lessons",
    "outline",
    "registration_policy",
    "refund_policy",
    "complaint_policy",
}


def test_detail_payload_names_a_field_for_every_applicable_item(
    client, db_session, admin_headers
):
    course, _ = make_published_course(db_session)
    detail = client.get(f"{PUBLIC_URL}/{course.course_code}").json()
    assert set(detail) == EXPECTED_DETAIL_KEYS
    assert detail["program_type"] == "Self study"
    assert detail["recommended_credit"] is not None
    # The 4.01 "most recent publication, revision, or review date".
    assert detail["last_documented_date"] is not None
    for key, kind in (
        ("registration_policy", "registration"),
        ("refund_policy", "refund"),
        ("complaint_policy", "complaint"),
    ):
        assert detail[key]["url"] == f"/policies#{kind}"
        assert detail[key]["effective_at"] is not None


def test_registry_words_absent_from_both_payloads_while_unclaimable(
    client, db_session, admin_headers
):
    course, _ = make_published_course(db_session)
    listing = client.get(PUBLIC_URL)
    detail = client.get(f"{PUBLIC_URL}/{course.course_code}")
    for response in (listing, detail):
        assert response.status_code == 200
        assert "National Registry" not in response.text
        assert "national_registry" not in response.text
    assert "sponsor_statement" not in detail.json()


def test_sponsor_statement_appears_once_claimable(
    client, db_session, admin_headers
):
    course, _ = make_published_course(db_session)
    claim_registry(db_session)
    detail = client.get(f"{PUBLIC_URL}/{course.course_code}").json()
    assert set(detail) == EXPECTED_DETAIL_KEYS | {"sponsor_statement"}
    assert detail["sponsor_statement"].startswith("SuperCPE LLC is registered")


def test_stale_credit_refuses_public_render_and_flags_the_admin_view(
    client, db_session, admin_headers
):
    course, _ = make_published_course(db_session)
    courses_service.touch(course)
    db_session.commit()
    # Refused, not served with a hole where item 3 belongs.
    assert client.get(PUBLIC_URL).json() == []
    assert client.get(f"{PUBLIC_URL}/{course.course_code}").status_code == 404
    # Flagged in the admin view, never auto-unpublished.
    admin_detail = client.get(
        f"/api/v1/admin/courses/{course.course_code}"
    ).json()
    assert admin_detail["status"] == "published"
    assert 3 in [i["number"] for i in admin_detail["disclosure_missing"]]


# --- site-mode behavior -------------------------------------------------------


def test_mode_matrix_for_catalog_and_detail(client, db_session, admin_account):
    course, _ = make_published_course(db_session)
    detail_url = f"{PUBLIC_URL}/{course.course_code}"

    # coming_soon, anonymous: both 404.
    assert client.get(PUBLIC_URL).status_code == 404
    assert client.get(detail_url).status_code == 404

    # coming_soon, any session: the admin preview of the disclosure page.
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.get(PUBLIC_URL).status_code == 200
    assert client.get(detail_url).status_code == 200

    # open: public.
    opened = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert opened.status_code == 200, opened.json()
    client.cookies.clear()
    assert client.get(PUBLIC_URL).status_code == 200
    assert client.get(detail_url).status_code == 200


def test_open_refused_while_nothing_is_published(
    client, db_session, admin_account, admin_headers
):
    publish_test_policies(db_session, admin_account)
    response = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert response.status_code == 422
    assert any(
        "No course is published" in e for e in response.json()["errors"]
    )


def test_open_refused_when_no_published_course_discloses_completely(
    client, db_session, admin_headers
):
    course, _ = make_published_course(db_session)
    # The dev-only path: a published course goes incomplete after the gate.
    course.description = ""
    db_session.commit()
    response = client.put(SITE_MODE_URL, json={"site_mode": "open"})
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(
        course.course_code in e and "8.01 item 7" in e for e in errors
    ), errors
