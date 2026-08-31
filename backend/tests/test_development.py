"""Feature 008: the development and review chain, and the publish gate."""

import re
from datetime import date, timedelta, timezone

import pytest

from app.models.review import CourseReview
from app.models.sme import SubjectMatterExpert
from app.services import development, readiness
from tests.conftest import publish_test_policies


@pytest.fixture(autouse=True)
def published_policies(db_session, admin_account):
    """016 made the 8.01 item 8-10 policies a publish requirement. Every
    test here is about the development findings, so the policy items are
    satisfied up front."""
    publish_test_policies(db_session, admin_account)
from tests.test_courses import (
    COURSES_URL,
    PUBLIC_URL,
    attach,
    get_detail,
    ingest,
    make_course,
)
from tests.test_credit import make_course_row, make_package_row

SMES_URL = "/api/v1/admin/smes"

# A review question plus assessment questions covering both factory
# objectives, so the 6.01.2 coverage check passes and nothing duplicates.
# Six questions in all: with the 2-second factory video, the question term
# (6 x 1.85 = 11.10 minutes) is what lifts the credit to 0.2, the minimum
# awardable — since 016 a course whose award is 0.0 fails 8.01 item 3 and
# cannot publish.
PUBLISHABLE_QUESTIONS = [
    {
        "id": "q-01",
        "kind": "review",
        "after_block": 1,
        "stem": "Is percentage of completion still a method?",
        "choices": [
            {"id": "a", "text": "Yes"},
            {"id": "b", "text": "No, it is a measure now"},
            {"id": "c", "text": "Only for construction"},
        ],
        "correct": "b",
        "feedback": "Re-study block 1.",
        "objective_ids": ["lo-1"],
    },
    {
        "id": "q-02",
        "kind": "assessment",
        "stem": "What replaced percentage of completion under ASC 606?",
        "choices": [
            {"id": "a", "text": "Nothing"},
            {"id": "b", "text": "Measures of progress"},
            {"id": "c", "text": "Cash basis"},
        ],
        "correct": "b",
        "feedback": "Measures of progress replaced it.",
        "objective_ids": ["lo-1"],
    },
    {
        "id": "q-03",
        "kind": "assessment",
        "stem": "Which measure depicts transfer of control?",
        "choices": [
            {"id": "a", "text": "Costs with no relation to progress"},
            {"id": "b", "text": "An output measure of units delivered"},
            {"id": "c", "text": "Cash collected"},
        ],
        "correct": "b",
        "feedback": "Output measures depict value transferred.",
        "objective_ids": ["lo-2"],
    },
    {
        "id": "q-04",
        "kind": "assessment",
        "stem": "What kind of measure is costs incurred to date?",
        "choices": [
            {"id": "a", "text": "An input measure"},
            {"id": "b", "text": "An output measure"},
            {"id": "c", "text": "Not a measure"},
        ],
        "correct": "a",
        "feedback": "Costs incurred are an input measure.",
        "objective_ids": ["lo-1"],
    },
    {
        "id": "q-05",
        "kind": "assessment",
        "stem": "When is an output measure preferable?",
        "choices": [
            {"id": "a", "text": "Never"},
            {"id": "b", "text": "When it faithfully depicts control transferred"},
            {"id": "c", "text": "Whenever costs are hard to track"},
        ],
        "correct": "b",
        "feedback": "Faithful depiction decides the measure.",
        "objective_ids": ["lo-2"],
    },
    {
        "id": "q-06",
        "kind": "assessment",
        "stem": "How is progress remeasured over the contract?",
        "choices": [
            {"id": "a", "text": "It is fixed at inception"},
            {"id": "b", "text": "Updated as circumstances change"},
            {"id": "c", "text": "Only on completion"},
        ],
        "correct": "b",
        "feedback": "Progress estimates are updated.",
        "objective_ids": ["lo-2"],
    },
]


def make_sme(client, headers, **overrides):
    body = {
        "name": "Dana Developer",
        "credentials": "CPA",
        "credential_type": "cpa",
        "license_jurisdiction": "NH",
        "license_number": "12345",
        "license_status": "active",
    }
    body.update(overrides)
    response = client.post(SMES_URL, json=body, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()


def set_developer(client, headers, code, sme_id, used_technology=True):
    return client.put(
        f"{COURSES_URL}/{code}/developer",
        json={"sme_id": sme_id, "used_technology": used_technology},
        headers=headers,
    )


def record_review(client, headers, code, reviewer_id, **overrides):
    body = {
        "reviewer_id": reviewer_id,
        "reviewed_at": date.today().isoformat(),
        "decision": "approved",
    }
    body.update(overrides)
    return client.post(
        f"{COURSES_URL}/{code}/reviews", json=body, headers=headers
    )


def set_price(client, headers, code, cents=4900):
    # 018: publish also requires a price (business rule).
    response = client.put(
        f"{COURSES_URL}/{code}/price",
        json={"price_cents": cents},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response


def publish(client, headers, code):
    return client.post(f"{COURSES_URL}/{code}/publish", headers=headers)


def unpublish(client, headers, code):
    return client.post(f"{COURSES_URL}/{code}/unpublish", headers=headers)


def make_publishable_course(client, headers, tmp_path):
    """A course that clears every block finding except the 008 development
    ones: description present, lesson attached, fresh credit, assessment
    covering both objectives."""
    package_id = ingest(
        client, headers, tmp_path, _questions=PUBLISHABLE_QUESTIONS
    )
    make_course(client, headers, description="Revenue recognition under ASC 606.")
    assert attach(client, headers, "ASC606-CON", package_id).status_code == 200
    set_price(client, headers, "ASC606-CON")
    return package_id


def add_chain(client, headers, code="ASC606-CON"):
    """Developer plus a distinct approved reviewer, both active CPAs."""
    developer = make_sme(client, headers, name="Dana Developer")
    reviewer = make_sme(client, headers, name="Rae Reviewer")
    assert set_developer(client, headers, code, developer["id"]).status_code == 200
    assert record_review(client, headers, code, reviewer["id"]).status_code == 201
    return developer, reviewer


# --- SME CRUD ---------------------------------------------------------------


def test_sme_crud(client, admin_headers):
    sme = make_sme(client, admin_headers)
    assert sme["license_status"] == "active"

    listed = client.get(SMES_URL, headers=admin_headers).json()
    assert [s["id"] for s in listed] == [sme["id"]]

    patched = client.patch(
        f"{SMES_URL}/{sme['id']}",
        json={"credentials": "CPA, MST", "license_status": "inactive"},
        headers=admin_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["credentials"] == "CPA, MST"
    assert patched.json()["license_status"] == "inactive"
    assert patched.json()["name"] == "Dana Developer"

    deleted = client.delete(f"{SMES_URL}/{sme['id']}", headers=admin_headers)
    assert deleted.status_code == 204
    assert client.get(SMES_URL, headers=admin_headers).json() == []


def test_sme_delete_refused_while_named(client, admin_headers, tmp_path):
    make_publishable_course(client, admin_headers, tmp_path)
    developer, reviewer = add_chain(client, admin_headers)

    response = client.delete(
        f"{SMES_URL}/{developer['id']}", headers=admin_headers
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "developer of record" in error and "ASC606-CON" in error

    response = client.delete(
        f"{SMES_URL}/{reviewer['id']}", headers=admin_headers
    )
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "reviewer" in error and "9.02.2(4)" in error


# --- The publish gate -------------------------------------------------------


def test_publish_refuses_with_every_block_finding_at_once(
    client, admin_headers, tmp_path
):
    package_id = ingest(
        client, admin_headers, tmp_path, _questions=PUBLISHABLE_QUESTIONS
    )
    make_course(client, admin_headers)  # blank description
    assert attach(client, admin_headers, "ASC606-CON", package_id).status_code == 200

    response = publish(client, admin_headers, "ASC606-CON")
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any("4.01.1" in e for e in errors)  # developer_missing
    assert any("No approved review" in e for e in errors)  # review_missing
    assert any("description is blank" in e for e in errors)
    # An Accounting course with no participants at all also fails 4.02.
    assert any("licensed CPA" in e for e in errors)
    # The blank description also fails the 016 disclosure check (item 7).
    assert any("8.01 item 7" in e for e in errors)
    # No price yet: the 018 business rule blocks too.
    assert any("business rule" in e for e in errors)
    assert len(errors) == 6

    detail = get_detail(client, admin_headers, "ASC606-CON")
    assert detail["status"] == "draft"


def test_complete_course_publishes_and_discloses_provenance(
    client, admin_headers, tmp_path
):
    make_publishable_course(client, admin_headers, tmp_path)
    developer, reviewer = add_chain(client, admin_headers)

    response = publish(client, admin_headers, "ASC606-CON")
    assert response.status_code == 200, response.json()
    detail = response.json()
    assert detail["status"] == "published"
    assert detail["development"]["published_at"] is not None
    assert detail["development"]["last_documented_date"] == date.today().isoformat()
    [review] = detail["development"]["reviews"]
    assert review["is_current"] is True
    assert review["is_superseded"] is False
    assert review["reviewer_name"] == "Rae Reviewer"

    [summary] = client.get(PUBLIC_URL).json()
    assert summary["developed_by"] == {"name": "Dana Developer", "credentials": "CPA"}
    assert summary["reviewed_by"] == {"name": "Rae Reviewer", "credentials": "CPA"}
    assert summary["last_reviewed"] == date.today().isoformat()
    assert summary["last_documented_date"] == date.today().isoformat()

    public = client.get(f"{PUBLIC_URL}/ASC606-CON")
    assert public.status_code == 200
    assert "license_number" not in public.text
    assert "12345" not in public.text


def test_reviewer_equal_to_developer_refused(client, admin_headers, tmp_path):
    make_publishable_course(client, admin_headers, tmp_path)
    sme = make_sme(client, admin_headers)
    assert set_developer(client, admin_headers, "ASC606-CON", sme["id"]).status_code == 200
    assert record_review(client, admin_headers, "ASC606-CON", sme["id"]).status_code == 201

    response = publish(client, admin_headers, "ASC606-CON")
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "other than those who developed" in error
    assert "Dana Developer" in error


def test_accounting_requires_an_active_cpa_participant(
    client, admin_headers, tmp_path
):
    make_publishable_course(client, admin_headers, tmp_path)  # Accounting
    developer = make_sme(
        client,
        admin_headers,
        name="Nona Numbers",
        credentials="MBA",
        credential_type="other",
        license_status="unknown",
        license_number="",
    )
    reviewer = make_sme(
        client,
        admin_headers,
        name="Ines Inactive",
        credential_type="cpa",
        license_status="inactive",
    )
    assert set_developer(client, admin_headers, "ASC606-CON", developer["id"]).status_code == 200
    assert record_review(client, admin_headers, "ASC606-CON", reviewer["id"]).status_code == 201

    response = publish(client, admin_headers, "ASC606-CON")
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "Accounting" in error and "4.02" in error and "active" in error

    # An active CPA license on the reviewer satisfies 4.02 in either role.
    client.patch(
        f"{SMES_URL}/{reviewer['id']}",
        json={"license_status": "active"},
        headers=admin_headers,
    )
    assert publish(client, admin_headers, "ASC606-CON").status_code == 200


def test_taxes_accepts_an_enrolled_agent(client, admin_headers, tmp_path):
    package_id = ingest(
        client,
        admin_headers,
        tmp_path,
        lesson_id="TAX-101-01",
        course_code="TAX-101",
        field_of_study="Taxes",
        _questions=PUBLISHABLE_QUESTIONS,
    )
    make_course(
        client,
        admin_headers,
        course_code="TAX-101",
        title="Federal Tax Update",
        description="What changed this year.",
    )
    assert attach(client, admin_headers, "TAX-101", package_id).status_code == 200
    set_price(client, admin_headers, "TAX-101")

    developer = make_sme(
        client,
        admin_headers,
        name="Tess Preparer",
        credentials="",
        credential_type="other",
        license_status="unknown",
        license_number="",
    )
    agent = make_sme(
        client,
        admin_headers,
        name="Ed Agent",
        credentials="EA",
        credential_type="enrolled_agent",
        license_jurisdiction="",
        license_number="EA-98765",
        license_status="active",
    )
    assert set_developer(client, admin_headers, "TAX-101", developer["id"]).status_code == 200
    assert record_review(client, admin_headers, "TAX-101", agent["id"]).status_code == 201

    assert publish(client, admin_headers, "TAX-101").status_code == 200


def test_content_change_supersedes_review(client, admin_headers, tmp_path):
    make_publishable_course(client, admin_headers, tmp_path)
    _, reviewer = add_chain(client, admin_headers)

    # A content edit after the review: the review no longer reviews what
    # the course says.
    edited = client.patch(
        f"{COURSES_URL}/ASC606-CON",
        json={"description": "Revenue recognition under ASC 606, revised."},
        headers=admin_headers,
    )
    assert edited.status_code == 200
    [review] = edited.json()["development"]["reviews"]
    assert review["is_current"] is False
    assert review["is_superseded"] is True

    response = publish(client, admin_headers, "ASC606-CON")
    assert response.status_code == 422
    [error] = response.json()["errors"]
    assert "content changed at" in error
    assert "reviewed the content as of" in error
    # Both timestamps are in the message.
    assert len(re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", error)) == 2

    assert record_review(client, admin_headers, "ASC606-CON", reviewer["id"]).status_code == 201
    assert publish(client, admin_headers, "ASC606-CON").status_code == 200


# --- Immutability of published courses --------------------------------------


def test_every_touch_path_refuses_on_a_published_course(
    client, admin_headers, tmp_path
):
    package_id = make_publishable_course(client, admin_headers, tmp_path)
    _, reviewer = add_chain(client, admin_headers)
    assert publish(client, admin_headers, "ASC606-CON").status_code == 200

    calls = [
        lambda: client.patch(
            f"{COURSES_URL}/ASC606-CON",
            json={"title": "New Title"},
            headers=admin_headers,
        ),
        lambda: client.post(
            f"{COURSES_URL}/ASC606-CON/lessons",
            json={"package_id": 999},
            headers=admin_headers,
        ),
        lambda: client.delete(
            f"{COURSES_URL}/ASC606-CON/lessons/{package_id}",
            headers=admin_headers,
        ),
        lambda: client.post(
            f"{COURSES_URL}/ASC606-CON/lessons/{package_id}/move",
            json={"direction": "up"},
            headers=admin_headers,
        ),
        lambda: client.post(
            f"{COURSES_URL}/ASC606-CON/lessons/{package_id}/update-version",
            json={"new_package_id": 999},
            headers=admin_headers,
        ),
    ]
    for call in calls:
        response = call()
        assert response.status_code == 422, response.json()
        [error] = response.json()["errors"]
        assert "immutable" in error and "unpublish" in error

    # Unpublish, edit, re-review, publish works end to end.
    assert unpublish(client, admin_headers, "ASC606-CON").status_code == 200
    assert client.patch(
        f"{COURSES_URL}/ASC606-CON",
        json={"title": "Revenue Under ASC 606, Second Look"},
        headers=admin_headers,
    ).status_code == 200
    stale = publish(client, admin_headers, "ASC606-CON")
    assert stale.status_code == 422
    assert any("content changed" in e for e in stale.json()["errors"])
    assert record_review(client, admin_headers, "ASC606-CON", reviewer["id"]).status_code == 201
    published = publish(client, admin_headers, "ASC606-CON")
    assert published.status_code == 200
    assert published.json()["development"]["unpublished_at"] is not None


def test_review_on_published_course_keeps_it_published_and_advances_dates(
    client, admin_headers, tmp_path
):
    make_publishable_course(client, admin_headers, tmp_path)
    _, reviewer = add_chain(client, admin_headers)
    assert publish(client, admin_headers, "ASC606-CON").status_code == 200

    later = (date.today() + timedelta(days=30)).isoformat()
    response = record_review(
        client, admin_headers, "ASC606-CON", reviewer["id"], reviewed_at=later
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "published"
    assert detail["development"]["last_documented_date"] == later
    current = [r for r in detail["development"]["reviews"] if r["is_current"]]
    assert [r["reviewed_at"] for r in current] == [later]

    [summary] = client.get(PUBLIC_URL).json()
    assert summary["last_reviewed"] == later
    assert summary["last_documented_date"] == later


# --- Derived dates ----------------------------------------------------------


def make_sme_row(db, **overrides):
    fields = {
        "name": "Dana Developer",
        "credentials": "CPA",
        "credential_type": "cpa",
        "license_status": "active",
    }
    fields.update(overrides)
    sme = SubjectMatterExpert(**fields)
    db.add(sme)
    db.commit()
    return sme


def make_review_row(db, course, reviewer, reviewed_at, decision="approved"):
    review = CourseReview(
        course_id=course.id,
        reviewer_id=reviewer.id,
        reviewed_at=reviewed_at,
        content_updated_at_reviewed=course.content_updated_at,
        decision=decision,
        recorded_by="admin",
    )
    db.add(review)
    db.commit()
    db.refresh(course)
    return review


def test_review_due_at_annual_vs_biennial(db_session):
    package = make_package_row(db_session)
    course = make_course_row(db_session, "GOLD", package)
    reviewer = make_sme_row(db_session)
    reviewed = date.today() - timedelta(days=400)
    make_review_row(db_session, course, reviewer, reviewed)

    assert development.review_due_at(course) == reviewed + timedelta(days=730)
    warns = [
        f for f in readiness.check(db_session, course) if f.code == "review_due"
    ]
    assert warns == []

    course.review_cycle = "annual"
    db_session.commit()
    assert development.review_due_at(course) == reviewed + timedelta(days=365)
    [warn] = [
        f for f in readiness.check(db_session, course) if f.code == "review_due"
    ]
    assert warn.level == "warn"
    assert "4.01" in warn.message


def test_changes_requested_review_is_not_current(db_session):
    package = make_package_row(db_session)
    course = make_course_row(db_session, "GOLD", package)
    reviewer = make_sme_row(db_session)
    make_review_row(
        db_session, course, reviewer, date.today(), decision="changes_requested"
    )

    assert development.current_review(course) is None
    assert development.review_due_at(course) is None
    # But the review date still counts as the 4.01 "most recent ... review
    # date" disclosure.
    assert development.last_documented_date(course) == date.today()
