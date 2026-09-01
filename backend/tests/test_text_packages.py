"""Feature 023: text-first course packages.

The acceptance criteria of current-feature.md, in order: computed word
counts that exclude what 7.02.5 excludes, a credit record whose three
terms are all live and re-add by hand, a reader that gates on review
questions without leaking the answer key, keyword search and a glossary
(4.05.3 items 2 and 3), and a publish gate that refuses without them.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.constants.review_attestation import ATTESTATION_VERSION
from app.services import courses as courses_service
from app.services import credit, development, packages, readiness
from app.services import questions as questions_service
from app.services.courses import DERIVED_FIELDS
from app.services.word_count import count_words
from app.storage import LocalStorage
from tests.conftest import login, publish_test_policies
from tests.factories.package import build_package
from tests.factories.text_package import (
    APPENDIX,
    BODY_ONE,
    BODY_ONE_WORDS,
    DEFAULT_COURSE_CODE,
    DEFAULT_LESSON_ID,
    DEFAULT_SECTION_FILES,
    build_text_package,
    default_glossary_terms,
    default_sections,
)
from tests.test_enrollments import (
    PARTICIPANT_EMAIL,
    PARTICIPANT_PASSWORD,
    enroll,
    make_participant,
    make_recorder,
    make_sme,
)

PACKAGES_URL = "/api/v1/admin/packages"


# --- helpers ---------------------------------------------------------------


def ingest_text(db, storage_root, tmp_path, **kwargs):
    """Validate and ingest the fixture text package, returning the row."""
    zip_path = build_text_package(tmp_path, **kwargs)
    result = packages.validate(zip_path)
    assert not isinstance(result, list), result
    package, _created = packages.ingest(
        db, LocalStorage(storage_root), result
    )
    return package, result


def errors_for(tmp_path, **kwargs) -> list[str]:
    result = packages.validate(build_text_package(tmp_path, **kwargs))
    assert isinstance(result, list), "expected refusal, package validated"
    return result


def attach_text_course(db, package, course_code=DEFAULT_COURSE_CODE):
    course = courses_service.create_course(
        db, course_code, "Identifying a Lease Under ASC 842"
    )
    courses_service.attach_package(db, course, package.id)
    db.refresh(course)
    return course


def make_publishable_text_course(db, package, course_code=DEFAULT_COURSE_CODE):
    """A text course that clears every publish gate: description,
    developer, an approved review by a second active CPA, a price, and the
    three 8.01 policies."""
    course = attach_text_course(db, package, course_code)
    for field in DERIVED_FIELDS:
        setattr(course, field, getattr(package, field))
    course.description = "Whether a contract contains a lease, under ASC 842."
    db.commit()
    courses_service.set_price(db, course, 4900)
    developer = make_sme(db, "Dev CPA")
    reviewer = make_sme(db, "Rev CPA")
    development.set_developer(db, course, developer.id, True)
    development.record_review(
        db, course, reviewer.id, date.today(), "approved",
        recorded_by=make_recorder(db),
    )
    publish_test_policies(db, make_recorder(db))
    credit.store(db, course.id)
    db.refresh(course)
    return course


def finding(findings, code):
    return next((f for f in findings if f.code == code), None)


# --- 1. ingestion computes the word count from body sections only ----------


def test_word_count_is_computed_from_body_sections_only(
    db_session, storage_root, tmp_path
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)

    assert package.kind == "text"
    assert package.word_count_source == "computed"

    # The per-section number matches a hand count of the section's prose
    # (the constant carries the arithmetic).
    body_one = next(s for s in package.sections if s.section_key == "sec-01")
    assert body_one.word_count == BODY_ONE_WORDS == count_words(BODY_ONE)

    # The total is exactly the body sections, and nothing else.
    body_total = sum(s.word_count for s in package.body_sections)
    assert package.word_count == body_total
    assert [s.section_key for s in package.body_sections] == [
        "sec-01",
        "sec-02",
        "sec-03",
    ]

    # Front matter, glossary, and appendix all shipped real words, and
    # none of them are in the total (7.02.5).
    excluded = [s for s in package.sections if not s.counted]
    assert {s.role for s in excluded} == {"front_matter", "glossary", "appendix"}
    assert all(s.word_count > 0 for s in excluded)
    assert package.word_count < sum(s.word_count for s in package.sections)


def test_a_thousand_words_of_appendix_do_not_move_the_count(
    db_session, storage_root, tmp_path
):
    """7.02.5 names appendixes of supplementary reference material as
    excluded. Proving it by re-ingesting a v2 whose appendix grew by a
    thousand words: the counted total must not move at all."""
    v1, _ = ingest_text(db_session, storage_root, tmp_path)

    fattened = dict(DEFAULT_SECTION_FILES)
    fattened["guide/91-appendix-a.md"] = (
        APPENDIX + "\n" + " ".join(f"word{n}" for n in range(1000)) + "\n"
    )
    v2, _ = ingest_text(
        db_session, storage_root, tmp_path, section_files=fattened
    )

    assert v2.version == v1.version + 1
    assert v2.content_hash != v1.content_hash

    was = next(s for s in v1.sections if s.section_key == "sec-91").word_count
    now = next(s for s in v2.sections if s.section_key == "sec-91").word_count
    assert now == was + 1000

    # The number that reaches the formula does not move at all.
    assert v2.word_count == v1.word_count


def test_reingesting_the_same_package_is_a_no_op(
    db_session, storage_root, tmp_path
):
    first, _ = ingest_text(db_session, storage_root, tmp_path)
    zip_path = build_text_package(tmp_path)
    result = packages.validate(zip_path)
    again, created = packages.ingest(
        db_session, LocalStorage(storage_root), result
    )
    assert created is False
    assert again.id == first.id


def test_sections_media_and_glossary_are_normalized(
    db_session, storage_root, tmp_path
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)

    assert [s.section_key for s in package.sections] == [
        s["id"] for s in default_sections()
    ]
    assert [s.position for s in package.sections] == [1, 2, 3, 4, 5, 6]

    assert len(package.media) == 1
    clip = package.media[0]
    assert clip.after_section == "sec-02"
    assert clip.duration_seconds == 2  # the 2 s fixture mp4, ffprobed here
    assert clip.av_is_additional_learning is True
    assert clip.storage_key == (
        f"packages/{DEFAULT_LESSON_ID}/v{package.version}/media/ex-01.mp4"
    )
    # The lesson's A/V duration is the sum of its clips (7.02.7).
    assert package.duration_seconds == 2
    # ...and it has no video of its own.
    assert package.video_key is None
    assert package.transcript is None
    assert package.measured_at is None

    assert [t.term for t in package.glossary_terms] == [
        t["term"] for t in default_glossary_terms()
    ]

    review = [
        q
        for q in questions_service.for_package(db_session, package.id)
        if q.kind == "review"
    ]
    assert len(review) == 5
    assert all(q.after_section is not None for q in review)
    assert all(q.after_block is None for q in review)


def test_media_lands_in_storage(db_session, storage_root, tmp_path):
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    storage = LocalStorage(storage_root)
    assert storage.exists(package.media[0].storage_key)


# --- ingestion refusals ----------------------------------------------------


def test_declared_word_count_is_refused(tmp_path):
    errors = errors_for(tmp_path, manifest_overrides={"word_count": 5000})
    assert any("must not declare a word count" in e for e in errors)


def test_narration_video_is_refused_with_the_7_02_7_sentence(tmp_path):
    errors = errors_for(
        tmp_path,
        manifest_overrides={
            "media": [
                {
                    "id": "vid-01",
                    "file": "media/ex-01.mp4",
                    "placement": {"after_section": "sec-02"},
                    "av_is_additional_learning": False,
                    "duration_seconds": None,
                }
            ]
        },
    )
    assert any("av_is_additional_learning: must be true" in e for e in errors)
    assert any("not narration of the text" in e for e in errors)


def test_no_body_section_is_refused(tmp_path):
    sections = default_sections()
    for section in sections:
        if section["role"] == "body":
            section["role"] = "appendix"
    errors = errors_for(tmp_path, manifest_overrides={"sections": sections})
    assert any("at least one 'body' section is required" in e for e in errors)


def test_unknown_section_role_is_refused(tmp_path):
    sections = default_sections()
    sections[1]["role"] = "bonus"
    errors = errors_for(tmp_path, manifest_overrides={"sections": sections})
    assert any('"bonus" is not one of' in e for e in errors)


def test_question_placed_at_a_missing_section_is_refused(tmp_path):
    from tests.factories.text_package import default_questions

    questions = default_questions()
    questions[0]["after_section"] = "sec-99"
    errors = errors_for(tmp_path, questions=questions)
    assert any(
        'after_section: "sec-99" is not a section id' in e for e in errors
    )


def test_media_placed_at_a_missing_section_is_refused(tmp_path):
    errors = errors_for(
        tmp_path,
        manifest_overrides={
            "media": [
                {
                    "id": "vid-01",
                    "file": "media/ex-01.mp4",
                    "placement": {"after_section": "nowhere"},
                    "av_is_additional_learning": True,
                    "duration_seconds": None,
                }
            ]
        },
    )
    assert any('"nowhere" is not a section id' in e for e in errors)


def test_a_section_file_missing_from_the_zip_is_refused(tmp_path):
    files = dict(DEFAULT_SECTION_FILES)
    del files["guide/02-identified-asset.md"]
    errors = errors_for(tmp_path, section_files=files)
    assert any(
        '"guide/02-identified-asset.md" is not in the package' in e
        for e in errors
    )


def test_a_markdown_file_the_manifest_does_not_name_is_refused(tmp_path):
    files = dict(DEFAULT_SECTION_FILES)
    files["guide/99-orphan.md"] = "# Orphan\n\nNever listed in the manifest.\n"
    errors = errors_for(tmp_path, section_files=files)
    assert any("guide/99-orphan.md is in the zip but not listed" in e for e in errors)


def test_tampered_content_hash_is_refused(tmp_path):
    errors = errors_for(
        tmp_path, manifest_overrides={"content_hash": "0" * 64}
    )
    assert any("content_hash: does not match" in e for e in errors)


def test_declared_media_duration_that_disagrees_is_refused(tmp_path):
    errors = errors_for(
        tmp_path,
        manifest_overrides={
            "media": [
                {
                    "id": "vid-01",
                    "file": "media/ex-01.mp4",
                    "placement": {"after_section": "sec-02"},
                    "av_is_additional_learning": True,
                    "duration_seconds": 600,
                }
            ]
        },
    )
    assert any("must agree within 1 second" in e for e in errors)


def test_empty_glossary_warns_but_ingests(db_session, storage_root, tmp_path):
    package, result = ingest_text(
        db_session,
        storage_root,
        tmp_path,
        manifest_overrides={"glossary_terms": []},
    )
    assert package.id is not None
    assert package.glossary_terms == []
    assert any("glossary_terms: empty" in w for w in result.warnings)


# --- 2. credit -------------------------------------------------------------


def test_all_three_terms_are_live_and_the_record_re_adds(
    db_session, storage_root, tmp_path
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = attach_text_course(db_session, package)
    breakdown = credit.store(db_session, course.id)

    # All three terms nonzero: words from the guide, A/V from the clip,
    # questions from both kinds.
    assert breakdown.word_count == package.word_count > 0
    assert breakdown.av_seconds == 2
    assert breakdown.question_count == 9
    assert breakdown.word_minutes > 0
    assert breakdown.av_minutes > 0
    assert breakdown.question_minutes > 0

    rendered = credit.as_text(breakdown)
    assert "computed from package text, body sections only, 7.02.5" in rendered
    assert "(supplemental, additional learning)" in rendered

    # The arithmetic re-adds by hand from the printed terms.
    by_hand = (
        breakdown.word_minutes
        + breakdown.av_minutes
        + breakdown.question_minutes
    )
    assert by_hand == breakdown.raw_minutes
    assert credit.round_down(by_hand / Decimal(50)) == breakdown.award
    assert f"{by_hand} / 50 = {breakdown.raw_credit} raw credit" in rendered

    # And the stored breakdown alone rebuilds the same record.
    db_session.refresh(course)
    assert credit.as_text(credit.from_stored(course)) == rendered


def test_video_only_lesson_now_says_the_program_is_the_video(db_session):
    """The B2 label fix. A video-kind lesson whose video is the whole
    program used to print "(additional learning)", which reads as a
    supplement to text it does not have; 7.02.7's second sentence is what
    is actually happening."""
    from tests.test_credit import make_course_row, make_package_row, questions_of

    package = make_package_row(
        db_session, questions=questions_of(review=2, assessment=2)
    )
    course = make_course_row(db_session, "VID", package)
    rendered = credit.as_text(credit.store(db_session, course.id))
    assert "(program is the video, 7.02.7)" in rendered
    assert "(additional learning)" not in rendered
    assert "(from manifest, trusted)" in rendered


def test_a_mixed_course_composes_per_lesson(
    db_session, storage_root, tmp_path
):
    """A course may attach both kinds; credit composes without special
    handling, and the record names each lesson's basis separately."""
    from tests.test_credit import make_package_row

    text_package, _ = ingest_text(db_session, storage_root, tmp_path)
    video_package = make_package_row(
        db_session,
        lesson_id=f"{DEFAULT_COURSE_CODE}-02",
        duration_seconds=600,
    )
    video_package.manifest = {
        **video_package.manifest,
        "course_code": DEFAULT_COURSE_CODE,
        "position": 2,
    }
    for field in DERIVED_FIELDS:
        setattr(video_package, field, getattr(text_package, field))
    db_session.commit()

    course = attach_text_course(db_session, text_package)
    courses_service.attach_package(db_session, course, video_package.id)
    breakdown = credit.store(db_session, course.id)

    assert breakdown.av_seconds == 2 + 600
    assert breakdown.word_count == text_package.word_count
    rendered = credit.as_text(breakdown)
    assert "computed from package text" in rendered
    assert "(from manifest, trusted)" in rendered


# --- 3, 4. the reader ------------------------------------------------------


@pytest.fixture
def reading_participant(db_session, storage_root, tmp_path, client):
    """An enrolled participant, logged in, on the fixture text course."""
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = make_publishable_text_course(db_session, package)
    courses_service.publish(db_session, course)
    account = make_participant(db_session)
    enrollment = enroll(db_session, course, account)
    login(client, PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD)
    return enrollment, package, course


def read(client, enrollment, package):
    response = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/lessons/{package.id}/read"
    )
    assert response.status_code == 200, response.text
    return response.json()


def answer(client, enrollment, package, question_key, choice_key="b"):
    return client.post(
        f"/api/v1/my/enrollments/{enrollment.id}/lessons/{package.id}"
        f"/review/{question_key}",
        json={"choice_key": choice_key},
    )


def test_the_next_body_section_is_locked_until_the_question_is_answered(
    client, reading_participant
):
    enrollment, package, _ = reading_participant
    payload = read(client, enrollment, package)
    by_key = {s["section_key"]: s for s in payload["sections"]}

    # sec-01 is open and carries a placed question; sec-02 and sec-03 are
    # not — and their text is not in the payload at all.
    assert by_key["sec-01"]["locked"] is False
    assert by_key["sec-01"]["markdown"]
    for key in ("sec-02", "sec-03"):
        assert by_key[key]["locked"] is True
        assert by_key[key]["markdown"] is None

    # Reference sections are reachable while the body is gated: 7.02.5
    # excludes them from the count for the same reason the reader does
    # not require them.
    for key in ("sec-00", "sec-90", "sec-91"):
        assert by_key[key]["locked"] is False
        assert by_key[key]["markdown"]

    # Two review questions are placed after sec-01, and *both* gate the
    # next section — in either order. Answering only one leaves it shut.
    assert by_key["sec-01"]["question_keys"] == ["q-r01", "q-r02"]

    assert answer(client, enrollment, package, "q-r02").status_code == 200
    still = {s["section_key"]: s for s in read(client, enrollment, package)["sections"]}
    assert still["sec-02"]["locked"] is True
    assert still["sec-02"]["markdown"] is None

    assert answer(client, enrollment, package, "q-r01").status_code == 200
    opened = {s["section_key"]: s for s in read(client, enrollment, package)["sections"]}
    assert opened["sec-02"]["locked"] is False
    assert opened["sec-02"]["markdown"]
    # ...and the gate has simply moved on to the next one.
    assert opened["sec-03"]["locked"] is True


def test_a_locked_sections_media_and_questions_are_withheld_too(
    client, reading_participant
):
    enrollment, package, _ = reading_participant
    payload = read(client, enrollment, package)
    # The clip is placed after sec-02, which is still locked.
    assert payload["media"] == []
    assert {q["after_section"] for q in payload["questions"]} == {"sec-01"}

    for key in ("q-r01", "q-r02", "q-r03", "q-r04"):
        assert answer(client, enrollment, package, key).status_code == 200
    opened = read(client, enrollment, package)
    assert [m["media_key"] for m in opened["media"]] == ["vid-01"]
    assert opened["media"][0]["after_section"] == "sec-02"


def test_reader_payload_never_carries_the_answer_key(
    client, reading_participant
):
    """The 006 rule, in the reader: no is_correct, no correct choice key,
    no feedback before an answer."""
    enrollment, package, _ = reading_participant
    for key in ("q-r01", "q-r02", "q-r03", "q-r04", "q-r05"):
        answer(client, enrollment, package, key)
    payload = read(client, enrollment, package)

    assert payload["questions"]
    for question in payload["questions"]:
        assert set(question) == {
            "question_key",
            "after_section",
            "stem",
            "choices",
            "answered",
        }
        assert question["choices"]
        for choice in question["choices"]:
            assert set(choice) == {"choice_key", "text"}

    blob = str(payload).lower()
    assert "is_correct" not in blob
    assert "feedback" not in blob
    assert "correct_choice" not in blob


def test_grading_a_reader_question_gives_feedback_and_records_it(
    client, reading_participant
):
    enrollment, package, _ = reading_participant
    response = answer(client, enrollment, package, "q-r01", "b")
    body = response.json()
    assert body["correct"] is True
    assert body["feedback"]  # 5.01.2.2: feedback either way
    assert body["correct_choice_key"] == "b"


def test_assessment_is_refused_while_review_questions_are_unanswered(
    client, db_session, reading_participant
):
    enrollment, package, _ = reading_participant
    info = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment"
    ).json()
    assert info["available"] is False
    named = " ".join(info["unavailable_reasons"])
    assert "q-r01" in named and "q-r05" in named

    for key in ("q-r01", "q-r02", "q-r03", "q-r04", "q-r05"):
        answer(client, enrollment, package, key)
    info = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/assessment"
    ).json()
    assert info["available"] is True
    assert info["unavailable_reasons"] == []


def test_the_reviewer_preview_is_ungated(
    client, db_session, storage_root, tmp_path, admin_headers
):
    """4.02 asks the reviewer to read the guide they sign off on, and
    there is no participant record to gate against."""
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = attach_text_course(db_session, package)
    payload = client.get(
        f"/api/v1/courses/{course.course_code}/lessons/{package.id}/read"
    ).json()
    assert all(s["locked"] is False for s in payload["sections"])
    assert all(s["markdown"] for s in payload["sections"])
    assert len(payload["questions"]) == 5


# --- 5. keyword search, 4.05.3 item 2 --------------------------------------


def test_search_finds_a_term_in_exactly_one_section(
    client, reading_participant
):
    enrollment, _package, _ = reading_participant
    response = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/search",
        params={"q": "substitution"},
    )
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert len(hits) == 1
    hit = hits[0]
    assert hit["section_key"] == "sec-02"
    assert hit["section_title"] == "Identified Asset"
    assert "substitution" in hit["snippets"][0].lower()


def test_search_returns_no_question_text(
    db_session, client, reading_participant
):
    """Answer-adjacent content stays out of any payload the browser can
    query. Not a filter — search reads `package_sections` and nothing
    else, so there is no question text in scope to leak."""
    enrollment, package, _ = reading_participant
    stems = [
        q.stem for q in questions_service.for_package(db_session, package.id)
    ]
    assert stems

    # Words that appear only in question stems and choices find nothing.
    # (Phrases like "review question" are deliberately not used here: the
    # front matter says them, and finding them there is the search
    # working, not leaking.)
    for query in ("Right answer", "Also wrong", "Assessment question 1"):
        assert (
            client.get(
                f"/api/v1/my/enrollments/{enrollment.id}/search",
                params={"q": query},
            ).json()["hits"]
            == []
        )

    # ...and no stem appears anywhere in a payload for a query that does
    # hit the guide.
    blob = str(
        client.get(
            f"/api/v1/my/enrollments/{enrollment.id}/search",
            params={"q": "lease"},
        ).json()
    )
    assert blob
    for stem in stems:
        assert stem not in blob


def test_search_is_scoped_to_the_guide_text(client, reading_participant):
    enrollment, _package, _ = reading_participant
    # A phrase that appears only in an assessment stem finds nothing.
    assert (
        client.get(
            f"/api/v1/my/enrollments/{enrollment.id}/search",
            params={"q": "Assessment question 2"},
        ).json()["hits"]
        == []
    )
    # A word in the guide finds its section.
    hits = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/search",
        params={"q": "economic benefits"},
    ).json()["hits"]
    assert [h["section_key"] for h in hits] == ["sec-01"]


def test_a_one_character_query_finds_nothing(client, reading_participant):
    enrollment, _package, _ = reading_participant
    assert (
        client.get(
            f"/api/v1/my/enrollments/{enrollment.id}/search", params={"q": "a"}
        ).json()["hits"]
        == []
    )


# --- 6. glossary, 4.05.3 item 3 --------------------------------------------


def test_glossary_page_renders_every_term(client, reading_participant):
    enrollment, _package, _ = reading_participant
    terms = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/glossary"
    ).json()["terms"]
    assert {t["term"] for t in terms} == {
        t["term"] for t in default_glossary_terms()
    }
    assert all(t["definition"] for t in terms)
    # Alphabetical, so a participant can find one by eye.
    assert [t["term"] for t in terms] == sorted(
        (t["term"] for t in terms), key=str.lower
    )


def test_in_reader_lookup_reaches_one_definition(client, reading_participant):
    """4.05.3 item 3's own example: "a search function that takes a
    participant to the definition of a key word"."""
    enrollment, _package, _ = reading_participant
    terms = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/glossary",
        params={"term": "right-of-use asset"},
    ).json()["terms"]
    assert len(terms) == 1
    assert terms[0]["term"] == "Right-of-use asset"
    assert "right to use an underlying asset" in terms[0]["definition"]


def test_lookup_matches_a_prefix_when_nothing_matches_exactly(
    client, reading_participant
):
    enrollment, _package, _ = reading_participant
    terms = client.get(
        f"/api/v1/my/enrollments/{enrollment.id}/glossary",
        params={"term": "identi"},
    ).json()["terms"]
    assert [t["term"] for t in terms] == ["Identified asset"]


# --- 7. the publish gate ---------------------------------------------------


def test_publishes_with_everything_present(
    db_session, storage_root, tmp_path
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = make_publishable_text_course(db_session, package)
    assert [f.code for f in readiness.check(db_session, course) if f.level == "block"] == []
    courses_service.publish(db_session, course)
    assert course.status == "published"


def test_refuses_without_glossary_terms_naming_4_05_3(
    db_session, storage_root, tmp_path
):
    package, _ = ingest_text(
        db_session,
        storage_root,
        tmp_path,
        manifest_overrides={"glossary_terms": []},
    )
    course = make_publishable_text_course(db_session, package)
    found = finding(readiness.check(db_session, course), "glossary_missing")
    assert found is not None and found.level == "block"
    assert "4.05.3 item 3" in found.message

    with pytest.raises(courses_service.CourseRuleViolation) as refusal:
        courses_service.publish(db_session, course)
    assert any("4.05.3 item 3" in e for e in refusal.value.errors)


def test_refuses_without_front_matter_naming_4_05_3(
    db_session, storage_root, tmp_path
):
    sections = [s for s in default_sections() if s["role"] != "front_matter"]
    files = {
        name: text
        for name, text in DEFAULT_SECTION_FILES.items()
        if name != "guide/00-front-matter.md"
    }
    package, _ = ingest_text(
        db_session,
        storage_root,
        tmp_path,
        manifest_overrides={"sections": sections},
        section_files=files,
    )
    course = make_publishable_text_course(db_session, package)
    found = finding(readiness.check(db_session, course), "front_matter_missing")
    assert found is not None and found.level == "block"
    assert "4.05.3 item 4" in found.message

    with pytest.raises(courses_service.CourseRuleViolation) as refusal:
        courses_service.publish(db_session, course)
    assert any("4.05.3 item 4" in e for e in refusal.value.errors)


def test_the_023_gates_accumulate(db_session, storage_root, tmp_path):
    """Block findings accumulate, like every other publish gate: a course
    missing two things is told about both at once."""
    sections = [s for s in default_sections() if s["role"] != "front_matter"]
    files = {
        name: text
        for name, text in DEFAULT_SECTION_FILES.items()
        if name != "guide/00-front-matter.md"
    }
    package, _ = ingest_text(
        db_session,
        storage_root,
        tmp_path,
        manifest_overrides={"sections": sections, "glossary_terms": []},
        section_files=files,
    )
    course = make_publishable_text_course(db_session, package)
    codes = {f.code for f in readiness.check(db_session, course)}
    assert {"glossary_missing", "front_matter_missing"} <= codes


def test_a_video_only_course_gains_no_023_findings(db_session):
    """Criterion 8, at the gate: nothing about 023 reaches a video
    course."""
    from tests.test_enrollments import make_publish_ready_course

    course, _ = make_publish_ready_course(db_session)
    codes = {f.code for f in readiness.check(db_session, course)}
    assert not (
        codes
        & {"glossary_missing", "front_matter_missing", "text_word_count_zero"}
    )


# --- B1: the package detail summary ----------------------------------------


def test_package_detail_summarizes_the_7_02_5_split(
    client, db_session, storage_root, tmp_path, admin_headers
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    detail = client.get(f"{PACKAGES_URL}/{package.id}").json()

    overview = detail["overview"]
    assert overview["kind"] == "text"
    assert overview["word_count_source"] == "computed"
    assert overview["word_count"] == package.word_count
    assert overview["total_words"] > overview["word_count"]
    assert overview["media_count"] == 1
    assert overview["media_seconds"] == 2
    assert overview["review_questions"] == 5
    assert overview["assessment_questions"] == 4

    by_role = {r["role"]: r for r in overview["sections_by_role"]}
    assert by_role["body"]["sections"] == 3
    assert by_role["body"]["counted"] is True
    for role in ("front_matter", "glossary", "appendix"):
        assert by_role[role]["counted"] is False
        assert by_role[role]["words"] > 0

    assert len(detail["sections"]) == 6
    assert len(detail["glossary_terms"]) == 5
    # The summary stands above the raw manifest, which is still served.
    assert detail["manifest"]["kind"] == "text"


def test_text_package_has_no_transcript_route(
    client, db_session, storage_root, tmp_path, admin_headers
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    assert client.get(f"{PACKAGES_URL}/{package.id}/transcript").status_code == 404
    section = client.get(f"{PACKAGES_URL}/{package.id}/sections/sec-01")
    assert section.status_code == 200
    assert section.text == BODY_ONE


def test_upload_reports_warnings(
    client, tmp_path, admin_headers
):
    zip_path = build_text_package(
        tmp_path, manifest_overrides={"glossary_terms": []}
    )
    with open(zip_path, "rb") as f:
        response = client.post(
            PACKAGES_URL, files={"file": ("p.zip", f, "application/zip")}
        )
    assert response.status_code == 201, response.text
    assert any("glossary_terms: empty" in w for w in response.json()["warnings"])


# --- B6: the reviewer's attestation ----------------------------------------


def test_review_sign_off_adds_the_text_lines(
    client, db_session, storage_root, tmp_path, admin_headers
):
    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = attach_text_course(db_session, package)
    detail = client.get(f"/api/v1/review/courses/{course.course_code}").json()

    assert detail["attestation_version"] == ATTESTATION_VERSION
    joined = " ".join(detail["attestation"])
    assert "7.02.7" in joined and "not narration of the text" in joined
    assert "7.02.5" in joined and "appendix" in joined
    assert detail["lessons"][0]["kind"] == "text"
    assert detail["lessons"][0]["word_count"] == package.word_count


def test_a_video_course_sign_off_keeps_the_base_lines_only(
    client, db_session, admin_headers
):
    from tests.test_enrollments import make_publish_ready_course

    course, _ = make_publish_ready_course(db_session)
    detail = client.get(f"/api/v1/review/courses/{course.course_code}").json()
    joined = " ".join(detail["attestation"])
    assert "7.02.7" not in joined
    assert "not narration of the text" not in joined
    assert detail["lessons"][0]["kind"] == "video"


# --- 8: the video package path is untouched --------------------------------


def test_a_video_package_still_ingests_unchanged(
    db_session, storage_root, tmp_path
):
    result = packages.validate(build_package(tmp_path))
    assert not isinstance(result, list), result
    package, created = packages.ingest(
        db_session, LocalStorage(storage_root), result
    )
    assert created is True
    assert package.kind == "video"
    assert package.word_count_source == "manifest"
    assert package.video_key.endswith("video.mp4")
    assert package.transcript
    assert package.measured_at is not None
    assert package.sections == []
    assert package.media == []
    assert package.glossary_terms == []


def test_an_explicit_video_kind_is_the_same_as_none(
    db_session, storage_root, tmp_path
):
    result = packages.validate(
        build_package(tmp_path, manifest_overrides={"kind": "video"})
    )
    assert not isinstance(result, list), result
    assert result.kind == "video"


def test_a_broken_text_manifest_still_gets_video_refusals(tmp_path):
    """The kind peek falls back to video when the manifest cannot be read,
    so a broken package gets the refusals it always got."""
    import zipfile

    zip_path = tmp_path / "broken.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("BROKEN/manifest.json", "{not json")
    errors = packages.validate(zip_path)
    assert any("missing required file BROKEN/video.mp4" in e for e in errors)


# --- 9.02.1(7): a text package's program materials in the audit bundle -----


def test_the_audit_bundle_carries_the_guide_and_its_word_count(
    db_session, storage_root, tmp_path
):
    """A text package's program materials are its guide, not a transcript
    of a video it does not have — and the 7.02.5 accounting that produced
    the word term of the retained calculation goes in beside it."""
    import zipfile
    import io

    from app.services import audit_bundle

    package, _ = ingest_text(db_session, storage_root, tmp_path)
    course = make_publishable_text_course(db_session, package)
    courses_service.publish(db_session, course)
    storage = LocalStorage(storage_root)

    content, _bundle_manifest = audit_bundle.build(
        db_session, storage, course, generated_by=make_recorder(db_session)
    )
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    # One top-level directory, named for the course and the day.
    files = {
        name.split("/", 1)[1]: data
        for name, data in files.items()
        if "/" in name
    }

    prefix = f"7-materials/{package.lesson_id}/v{package.version}"
    # Every section, under the file name the author wrote it as.
    for name in DEFAULT_SECTION_FILES:
        assert f"{prefix}/{name}" in files
    assert files[f"{prefix}/guide/01-identifying-a-lease.md"].decode() == BODY_ONE

    # No transcript and no video note: this package has neither.
    assert f"{prefix}/transcript.md" not in files
    assert f"{prefix}/video.txt" not in files

    # The supplemental clip is present by reference, like a lesson video.
    note = files[f"{prefix}/media/ex-01.mp4.txt"].decode()
    assert package.media[0].storage_key in note
    assert "av_is_additional_learning: true (7.02.7)" in note

    # The 7.02.5 accounting behind the word term.
    accounting = files[f"{prefix}/word-count.txt"].decode()
    assert f"Counted (body sections only): {package.word_count}" in accounting
    assert "counted " in accounting and "excluded" in accounting
    assert "guide/91-appendix-a.md" in accounting
