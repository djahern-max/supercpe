"""Feature 006: the play payload, server-side review grading, and the
answer key never reaching the browser.

abacadaba shipped the answer key to the browser once and had to build a
replay test to prove it was gone; here `walk_asserting_no_answer_key` walks
every payload the player and the admin question view receive.
"""

from tests.test_courses import COURSES_URL, attach, ingest, make_course


def play_url(course_code, package_id):
    return f"/api/v1/courses/{course_code}/lessons/{package_id}/play"


def review_url(course_code, package_id, question_key):
    return f"/api/v1/courses/{course_code}/lessons/{package_id}/review/{question_key}"


def setup_course(client, admin_headers, tmp_path):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    response = attach(client, admin_headers, "ASC606-CON", package_id)
    assert response.status_code == 200
    return package_id


def walk_asserting_no_answer_key(node, path="$"):
    """The answer key must be absent from the whole payload: no is_correct,
    no correct, and no feedback before an answer is submitted."""
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in ("is_correct", "correct", "correct_choice_key"), (
                f"answer key field {key!r} at {path}"
            )
            walk_asserting_no_answer_key(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk_asserting_no_answer_key(value, f"{path}[{i}]")


def test_play_payload(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    response = client.get(play_url("ASC606-CON", package_id), headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["lesson_id"] == "ASC606-CON-01"
    assert body["video_url"] == "/api/v1/media/packages/ASC606-CON-01/v1/video.mp4"
    assert [b["id"] for b in body["blocks"]] == ["block-01", "block-02", "block-03"]
    assert body["blocks"][0]["end_seconds"] == 0.6
    # Review questions only; the factory's assessment question stays out.
    assert [q["question_key"] for q in body["questions"]] == ["q-01"]
    question = body["questions"][0]
    assert question["after_block"] == 1
    assert [c["choice_key"] for c in question["choices"]] == ["a", "b", "c"]
    walk_asserting_no_answer_key(body)
    assert "feedback" not in str(body)


def test_play_video_url_serves_the_video(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    body = client.get(
        play_url("ASC606-CON", package_id), headers=admin_headers
    ).json()
    media = client.get(body["video_url"])
    assert media.status_code == 200
    assert media.headers["content-type"] == "video/mp4"


def test_play_requires_session(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    client.cookies.clear()
    assert client.get(play_url("ASC606-CON", package_id)).status_code == 401


def test_play_unattached_package_404(client, admin_headers, tmp_path):
    package_id = ingest(client, admin_headers, tmp_path)
    make_course(client, admin_headers)
    response = client.get(play_url("ASC606-CON", package_id), headers=admin_headers)
    assert response.status_code == 404


def test_grade_correct_answer(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    response = client.post(
        review_url("ASC606-CON", package_id, "q-01"),
        json={"choice_key": "b"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["correct"] is True
    assert body["correct_choice_key"] == "b"
    # 5.01.2.2: feedback always, not only on wrong answers.
    assert body["feedback"].strip()


def test_grade_incorrect_answer(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    response = client.post(
        review_url("ASC606-CON", package_id, "q-01"),
        json={"choice_key": "a"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["correct"] is False
    assert body["correct_choice_key"] == "b"
    assert body["feedback"].strip()


def test_grade_is_stateless_and_reanswerable(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    url = review_url("ASC606-CON", package_id, "q-01")
    first = client.post(url, json={"choice_key": "a"}, headers=admin_headers)
    second = client.post(url, json={"choice_key": "b"}, headers=admin_headers)
    assert first.json()["correct"] is False
    assert second.json()["correct"] is True


def test_grade_unknown_choice_422(client, admin_headers, tmp_path):
    package_id = setup_course(client, admin_headers, tmp_path)
    response = client.post(
        review_url("ASC606-CON", package_id, "q-01"),
        json={"choice_key": "z"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert any("z" in e for e in response.json()["errors"])


def test_grade_assessment_question_404(client, admin_headers, tmp_path):
    """The factory's q-02 is an assessment question; grading it here would
    leak 007's territory (6.01.2 has different feedback rules)."""
    package_id = setup_course(client, admin_headers, tmp_path)
    response = client.post(
        review_url("ASC606-CON", package_id, "q-02"),
        json={"choice_key": "b"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_admin_question_payload_has_no_answer_key(client, admin_headers, tmp_path):
    setup_course(client, admin_headers, tmp_path)
    response = client.get(f"{COURSES_URL}/ASC606-CON", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    walk_asserting_no_answer_key(body["questions"])
    walk_asserting_no_answer_key(body["readiness"])
    [group] = body["questions"]
    assert group["lesson_id"] == "ASC606-CON-01"
    assert [q["question_key"] for q in group["review"]] == ["q-01"]
    assert [q["question_key"] for q in group["assessment"]] == ["q-02"]
    assert group["review"][0]["counts_toward_minimum"] is True
    assert group["review"][0]["choice_count"] == 3


# --- 031: `answered` on each review question in the play payload -----------------


def test_preview_play_payload_marks_every_question_unanswered(
    client, admin_headers, tmp_path
):
    """Nothing a previewer does is recorded (006), so the flag is False on
    every load — even right after grading an answer through the preview
    route."""
    package_id = setup_course(client, admin_headers, tmp_path)
    client.post(
        review_url("ASC606-CON", package_id, "q-01"),
        json={"choice_key": "b"},
        headers=admin_headers,
    )
    body = client.get(play_url("ASC606-CON", package_id), headers=admin_headers).json()
    assert [(q["question_key"], q["answered"]) for q in body["questions"]] == [
        ("q-01", False)
    ]
    walk_asserting_no_answer_key(body)


def test_enrollment_play_payload_derives_answered_from_review_answers(
    client, db_session
):
    """The enrollment path: one review_answers row → that question True,
    the rest False; derived exactly as the reader payload derives it."""
    from tests.test_enrollments import play_url as my_play_url
    from tests.test_enrollments import review_url as my_review_url
    from tests.test_enrollments import setup_enrolled

    _, package, enrollment = setup_enrolled(client, db_session)
    before = client.get(my_play_url(enrollment.id, package.id)).json()
    keys = [q["question_key"] for q in before["questions"]]
    assert len(keys) >= 2
    assert all(q["answered"] is False for q in before["questions"])

    graded = client.post(
        my_review_url(enrollment.id, package.id, keys[0]),
        json={"choice_key": "b"},
    )
    assert graded.status_code == 200

    after = client.get(my_play_url(enrollment.id, package.id)).json()
    flags = {q["question_key"]: q["answered"] for q in after["questions"]}
    assert flags[keys[0]] is True
    assert all(flags[key] is False for key in keys[1:])
    # A wrong answer counts as answered: the record is of engagement, not
    # of correctness (5.01.2.1 sets no passing rate).
    assert graded.json()["correct"] is False
    walk_asserting_no_answer_key(after)
