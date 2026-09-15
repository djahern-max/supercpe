"""Feature 035: catalog artwork.

The artwork is business metadata, not course content (like the price,
018): setting it never calls `touch`, so a published course keeps its
credit, its current review, and its published status. The public route
serves the bytes from the private bucket under an immutable cache header
whose safety rests entirely on the content hash being in the URL — the
tests below pin both halves of that bargain.
"""

import hashlib
import io
import os

import pytest
from PIL import Image

from app.constants.media import (
    THUMBNAIL_CACHE_SECONDS,
    THUMBNAIL_MAX_BYTES,
    THUMBNAIL_MAX_EDGE,
    THUMBNAIL_MIN_EDGE,
)
from app.services import courses as courses_service
from app.services import credit, development
from tests.test_enrollments import make_publish_ready_course, make_published_course
from tests.test_site import open_the_site

ADMIN_URL = "/api/v1/admin/courses"
PUBLIC_URL = "/api/v1/courses"


def png_bytes(width=1280, height=720, color=(1, 38, 96)):
    """A real PNG of the given size — the dimension checks read the
    header, so a hand-rolled stub would not do."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(width=1280, height=720):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (1, 176, 169)).save(buffer, format="JPEG")
    return buffer.getvalue()


def put_artwork(client, code, content, filename="artwork.png", content_type="image/png"):
    return client.put(
        f"{ADMIN_URL}/{code}/thumbnail",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


@pytest.fixture
def published(client, db_session, admin_headers):
    """A published course with the site open, so the public route is
    reachable anonymously once the client's cookies are cleared."""
    course, _package = make_published_course(db_session, "GOLD")
    open_the_site(client)
    return course


# --- ingest ------------------------------------------------------------------


def test_valid_png_lands_at_the_hashed_key_and_url_carries_the_hash(
    client, db_session, storage_root, published
):
    content = png_bytes()
    digest = hashlib.sha256(content).hexdigest()

    response = put_artwork(client, "GOLD", content)
    assert response.status_code == 200, response.json()

    expected_key = f"course-thumbnails/GOLD/{digest}.png"
    assert response.json()["thumbnail_key"] == expected_key
    assert (storage_root / expected_key).is_file()
    assert (storage_root / expected_key).read_bytes() == content

    url = response.json()["thumbnail_url"]
    assert url == f"/api/v1/courses/GOLD/thumbnail?v={digest[:12]}"

    db_session.refresh(published)
    assert published.thumbnail_key == expected_key


def test_public_payloads_carry_the_url_and_null_without_artwork(
    client, published
):
    summary = client.get(PUBLIC_URL).json()[0]
    assert summary["thumbnail_url"] is None
    assert client.get(f"{PUBLIC_URL}/GOLD").json()["thumbnail_url"] is None

    put_artwork(client, "GOLD", png_bytes())

    summary = client.get(PUBLIC_URL).json()[0]
    detail = client.get(f"{PUBLIC_URL}/GOLD").json()
    assert summary["thumbnail_url"].startswith(
        "/api/v1/courses/GOLD/thumbnail?v="
    )
    assert detail["thumbnail_url"] == summary["thumbnail_url"]


def test_jpeg_and_webp_are_accepted_by_their_bytes(client, published):
    assert put_artwork(
        client, "GOLD", jpeg_bytes(), "artwork.jpg", "image/jpeg"
    ).status_code == 200
    assert client.get(f"{ADMIN_URL}/GOLD").json()["thumbnail_key"].endswith(".jpg")

    buffer = io.BytesIO()
    Image.new("RGB", (1280, 720), (1, 102, 252)).save(buffer, format="WEBP")
    assert put_artwork(
        client, "GOLD", buffer.getvalue(), "artwork.webp", "image/webp"
    ).status_code == 200
    assert client.get(f"{ADMIN_URL}/GOLD").json()["thumbnail_key"].endswith(".webp")


def test_replacing_deletes_the_previous_object_and_changes_the_url(
    client, storage_root, published
):
    first = put_artwork(client, "GOLD", png_bytes(color=(1, 38, 96))).json()
    second = put_artwork(client, "GOLD", png_bytes(color=(1, 176, 169))).json()

    assert second["thumbnail_key"] != first["thumbnail_key"]
    assert second["thumbnail_url"] != first["thumbnail_url"]
    assert not (storage_root / first["thumbnail_key"]).exists()
    assert (storage_root / second["thumbnail_key"]).is_file()


def test_re_uploading_identical_bytes_keeps_the_same_key_and_object(
    client, storage_root, published
):
    """The key is the content hash, so the same bytes are the same URL —
    and the object must survive, not be deleted as "superseded" by
    itself."""
    content = png_bytes()
    first = put_artwork(client, "GOLD", content).json()
    second = put_artwork(client, "GOLD", content).json()

    assert second["thumbnail_key"] == first["thumbnail_key"]
    assert (storage_root / second["thumbnail_key"]).is_file()


def test_removing_artwork_deletes_the_object_and_nulls_the_payload(
    client, storage_root, published
):
    key = put_artwork(client, "GOLD", png_bytes()).json()["thumbnail_key"]

    response = client.delete(f"{ADMIN_URL}/GOLD/thumbnail")
    assert response.status_code == 200, response.json()
    assert response.json()["thumbnail_key"] is None
    assert response.json()["thumbnail_url"] is None
    assert not (storage_root / key).exists()


# --- refusals ----------------------------------------------------------------


def test_over_size_upload_is_refused_naming_the_limit(client, published):
    # Random-looking bytes so PNG compression cannot shrink it under the
    # cap; the router refuses on length before anything is decoded.
    oversize = b"\x89PNG\r\n\x1a\n" + os.urandom(THUMBNAIL_MAX_BYTES)
    response = put_artwork(client, "GOLD", oversize)
    assert response.status_code == 422
    assert response.json()["errors"] == [
        f"The artwork must be {THUMBNAIL_MAX_BYTES // (1024 * 1024)} MB or smaller."
    ]
    assert client.get(f"{ADMIN_URL}/GOLD").json()["thumbnail_key"] is None


def test_wrong_type_is_refused(client, published):
    response = put_artwork(
        client, "GOLD", b"GIF89a" + b"\x00" * 64, "artwork.gif", "image/gif"
    )
    assert response.status_code == 422
    assert "JPEG, PNG, or WebP" in response.json()["errors"][0]


def test_png_extension_over_non_png_bytes_is_refused(client, published):
    """The multipart content-type and the filename both say png; the
    bytes do not, and the bytes decide."""
    response = put_artwork(
        client, "GOLD", b"this is a text file, honestly", "artwork.png", "image/png"
    )
    assert response.status_code == 422
    assert "JPEG, PNG, or WebP" in response.json()["errors"][0]
    assert client.get(f"{ADMIN_URL}/GOLD").json()["thumbnail_key"] is None


def test_under_the_minimum_edge_is_refused_naming_the_limit(client, published):
    response = put_artwork(client, "GOLD", png_bytes(1024, 400))
    assert response.status_code == 422
    assert response.json()["errors"] == [
        f"The artwork is 1024x400; its shortest edge must be at least "
        f"{THUMBNAIL_MIN_EDGE} pixels."
    ]


def test_over_the_maximum_edge_is_refused_naming_the_limit(client, published):
    response = put_artwork(client, "GOLD", png_bytes(4200, 2400))
    assert response.status_code == 422
    assert response.json()["errors"] == [
        f"The artwork is 4200x2400; its longest edge must be at most "
        f"{THUMBNAIL_MAX_EDGE} pixels."
    ]


# --- artwork is not content --------------------------------------------------


def test_set_thumbnail_does_not_touch_content_or_unsettle_the_review(
    client, db_session, storage_root, published
):
    before = published.content_updated_at
    assert not credit.is_stale(published)

    assert put_artwork(client, "GOLD", png_bytes()).status_code == 200
    db_session.refresh(published)

    assert published.content_updated_at == before
    assert published.status == "published"
    assert not credit.is_stale(published)
    assert development.current_review(published) is not None

    # And removing it is just as quiet.
    assert client.delete(f"{ADMIN_URL}/GOLD/thumbnail").status_code == 200
    db_session.refresh(published)
    assert published.content_updated_at == before
    assert published.status == "published"
    assert not credit.is_stale(published)


def test_a_published_course_accepts_artwork_where_it_refuses_content(
    client, published
):
    """The immutability rule that refuses a title edit must not refuse a
    picture: that is the whole point of calling it a business fact."""
    refused = client.patch(
        f"{ADMIN_URL}/GOLD", json={"title": "A New Title"}
    )
    assert refused.status_code == 422
    assert "immutable" in refused.json()["errors"][0]

    assert put_artwork(client, "GOLD", png_bytes()).status_code == 200


# --- the public route --------------------------------------------------------


def test_public_get_serves_the_bytes_with_the_immutable_header_and_etag(
    client, published
):
    content = png_bytes()
    url = put_artwork(client, "GOLD", content).json()["thumbnail_url"]
    client.cookies.clear()

    response = client.get(url)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == (
        f"public, max-age={THUMBNAIL_CACHE_SECONDS}, immutable"
    )

    assert response.headers["etag"] == f'"{hashlib.sha256(content).hexdigest()}"'


def test_conditional_request_with_the_etag_is_304(client, published):
    url = put_artwork(client, "GOLD", png_bytes()).json()["thumbnail_url"]
    client.cookies.clear()

    etag = client.get(url).headers["etag"]
    response = client.get(url, headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    assert "immutable" in response.headers["cache-control"]

    # A list of tags is legal in the header and must still match.
    listed = client.get(url, headers={"If-None-Match": f'"other", {etag}'})
    assert listed.status_code == 304


def test_public_get_404s_without_artwork_and_for_an_unknown_course(
    client, published
):
    client.cookies.clear()
    assert client.get(f"{PUBLIC_URL}/GOLD/thumbnail").status_code == 404
    assert client.get(f"{PUBLIC_URL}/NOPE/thumbnail").status_code == 404


def test_public_get_404s_for_a_draft_course(client, db_session, published):
    """Artwork on an unpublished course is not public, and the miss is
    the same 404 as a course that does not exist. The site is open (the
    `published` fixture's GOLD is what lets it be), so the only thing
    keeping DRAFT1's picture private is its status."""
    course, _package = make_publish_ready_course(db_session, "DRAFT1")
    assert course.status == "draft"
    assert put_artwork(client, "DRAFT1", png_bytes()).status_code == 200

    url = client.get(f"{ADMIN_URL}/DRAFT1").json()["thumbnail_url"]
    client.cookies.clear()
    assert client.get(url).status_code == 404


def test_public_get_404s_anonymously_under_coming_soon(
    client, db_session, admin_headers
):
    """The site-mode gate on the whole router: an image that reveals a
    course title would defeat coming_soon as surely as the title. The
    admin's own session still gets through, which is how the gate has
    always behaved."""
    make_published_course(db_session, "GOLD")
    url = put_artwork(client, "GOLD", png_bytes()).json()["thumbnail_url"]
    assert client.get(url).status_code == 200  # the admin session

    client.cookies.clear()
    assert client.get(url).status_code == 404


def test_deleting_the_course_removes_the_object(
    client, db_session, storage_root, admin_headers
):
    make_publish_ready_course(db_session, "DOOMED")
    key = put_artwork(client, "DOOMED", png_bytes()).json()["thumbnail_key"]
    assert (storage_root / key).is_file()

    assert client.delete(f"{ADMIN_URL}/DOOMED").status_code == 204
    assert not (storage_root / key).exists()


def test_admin_routes_401_without_the_session(client, db_session, admin_headers):
    make_published_course(db_session, "GOLD")
    client.cookies.clear()

    assert put_artwork(client, "GOLD", png_bytes()).status_code == 401
    assert client.delete(f"{ADMIN_URL}/GOLD/thumbnail").status_code == 401


# --- the key is not mirrored -------------------------------------------------


def test_the_thumbnail_prefix_is_not_mirrored_off_site(client):
    """9.02 material is mirrored; marketing artwork is evidence of
    nothing and stays out of the off-site copy."""
    from app.constants.storage import MIRRORED_PREFIXES

    assert not any(
        prefix.startswith(courses_service.THUMBNAIL_KEY_PREFIX)
        or courses_service.THUMBNAIL_KEY_PREFIX.startswith(prefix.rstrip("/"))
        for prefix in MIRRORED_PREFIXES
    )
