# Current Feature

## Feature NN, Course thumbnails and the catalog card

> Set NN from the last entry in `CHANGELOG.md` before starting.

## Goal
Each course carries its own catalog artwork, uploaded by an admin, stored in
Spaces, and served from a cacheable public route. `/courses` stops being a
stack of paragraphs and becomes a scannable list that works on a phone.

## In scope
- `thumbnail_key` on `courses`, nullable, with its migration
- Admin upload and replace on the course detail page
- A public route serving the image, private bucket preserved
- `thumbnail_url` on the public course summary and detail payloads
- A rebuilt `/courses` catalog card, responsive to 360px
- First rows in `COMPLIANCE.md` only if a Standards paragraph is touched
  (8.01.1 is the candidate; artwork is not a disclosure element, so if
  nothing is touched, say so in the changelog rather than inventing a row)

## Out of scope
- `docs/course-package.md`. Artwork is admin-typed marketing metadata, not
  package content. video-tool has no business knowing what the storefront
  looks like, and the contract is the only thing the two repos share.
- Per-lesson artwork. A thumbnail has no lesson and no version.
- Image processing: no resizing, cropping, or format conversion server-side.
  The admin uploads what they want shown; CSS handles the fit.
- Any change to publish gates, review, credit, or `touch` semantics beyond
  the stated decision below.

## Decisions, stated rather than discovered
1. **No `touch`.** `set_price` is the precedent and its docstring is almost
   verbatim what applies here: a business fact, not course content. Swapping
   an image must not mark the credit stale or force a re-review. Published
   courses are immutable reads the other way until this is named, so name it
   in the docstring of the setter.
2. **API route, not presigned.** `storage.py` states the bucket is private
   and nothing is served from it directly. A presigned catalog URL churns
   hourly, defeating browser and CDN caching on an anonymous marketing page.
   Add `GET /api/v1/courses/{course_code}/thumbnail` streaming from
   `storage.open()`. Works identically under `LocalStorage` and
   `SpacesStorage` with no media special-casing.
3. **Cache-busting by content, not by time.** The stored key is
   `course-thumbnails/<course_code>/<sha256>.<ext>`, and `thumbnail_url` is
   the route with `?v=<first 12 of the sha256>`. That makes the response
   safely `Cache-Control: public, max-age=31536000, immutable` while a
   replacement changes the URL. Do not serve a stable URL with a short TTL.
4. **Replacement deletes the old object.** Artwork is regenerable; there is
   no retention interest in a superseded image. Deleting a course deletes
   its thumbnail object too.
5. **Not mirrored.** Stay out of `MIRRORED_PREFIXES`. That constant covers
   9.02 material; marketing artwork is not evidence of anything.
6. **`coming_soon` holds.** The route 404s anonymously while the site is in
   `coming_soon` and does not join `INTENTIONALLY_PUBLIC`. An image that
   reveals a course title defeats the gate.

## Backend tasks
1. `app/constants/media.py`, marked "ours" (not from the Standards):
   allowed content types `image/jpeg`, `image/png`, `image/webp`; max 2 MiB;
   max edge 4000px; min edge 600px. Sniff the magic bytes — do not trust the
   multipart `content-type` header.
2. `app/models/course.py`: `thumbnail_key: Mapped[str | None]`. Autogenerate
   the migration, verify `downgrade -1`.
3. `app/services/courses.py`: `set_thumbnail(db, storage, code, upload)` and
   `clear_thumbnail(db, storage, code)`. Validation failures raise
   `CourseRuleViolation` so they surface in the same 422 `{"errors": [...]}`
   shape as everything else. Both delete the superseded object. Neither
   calls `touch`. `delete_course` removes the object.
4. Routers: `PUT` and `DELETE /api/v1/admin/courses/{code}/thumbnail` under
   the admin dependency; public `GET /api/v1/courses/{code}/thumbnail`
   returning the bytes with the content type, the immutable cache header,
   and an `ETag` of the hash. 404 when the course has no thumbnail, when the
   course is not published, and anonymously under `coming_soon`.
5. `app/schemas/course.py`: `thumbnail_url: str | None` on
   `PublicCourseSummary` and the public detail schema. Null when unset —
   most courses will have none on day one.

## Frontend tasks
1. `src/api/admin.js`: `setCourseThumbnail(code, file)` reusing the existing
   `FormData` pattern; `clearCourseThumbnail(code)`.
2. `AdminCourseDetail`: an artwork card — current image, file picker,
   Replace, Remove. Show the constants' limits as text before upload, and
   render 422 messages per line as elsewhere. Copy: "Catalog artwork",
   "Upload artwork", "Remove artwork" — the button says what happens.
3. `Catalog.jsx`: the card below. Degrade cleanly when `thumbnail_url` is
   null — the card keeps its shape and the text column takes the full width.
   No placeholder graphic, no grey box with an icon.

## Design brief for the catalog card
The audience is a licensed CPA deciding whether to spend an hour and $29.
The one fact they scan for is the credit amount. Spend the boldness there
and keep everything else quiet.

**Tokens.** Ground: `#F5F7FA`. Card: `#FFFFFF`. Ink: `#032660` (the logo
navy) for headings, `#44506A` for body. Accent: `#0166FC` for links and the
credit figure. `#01B0A9` exists in the brand but is not needed here — leave
it for the reader UI so the catalog stays calm.

**Type.** Inter throughout, matching the video theme, so a participant sees
one typeface from catalog to certificate. Title 20/1.3 semibold, body
15/1.55, metadata 13. Description clamped to two lines; the full text lives
on the course page.

**Layout.** A horizontal card, not a grid of tiles: artwork left at 16:9 and
about 240px wide, text right, price top-right of the text column. This holds
up at one course and at twelve, where a 3-up grid looks broken at one. Below
640px the artwork moves above the text at full width and the price moves
under the title. Max content width 860px, left aligned.

**Metadata.** Drop the dot-joined string. Credits become their own element —
`3.2 credits` at 17px in the accent colour, beside the price. The rest
(field of study, Basic, 6 lessons, 39 sections, 7 min video) becomes one
quiet 13px line in `#44506A`. Do not make them chips; five bordered pills is
more structure than five plain facts deserve.

**Restraint.** No hover lift, no shadow beyond a 1px `#E3E8F0` border, no
scroll-triggered fades. The only motion is focus and the image loading.
`alt=""` on the artwork — the title beside it is the accessible name, and a
described decoration is noise for a screen reader. Visible keyboard focus on
the whole card link.

**Empty state.** One sentence in body type: "No courses are published yet."

## Tests (`tests/test_course_thumbnails.py`)
- valid png ingests; object at the expected key; `thumbnail_url` carries the
  `v` parameter matching the hash
- replacing deletes the previous object and changes `thumbnail_url`
- over-size, wrong type, and a `.png` whose bytes are not a png are each
  refused with a message naming the limit
- a file under the minimum edge is refused
- `set_thumbnail` does not change `content_updated_at`; a published course
  stays published and its review stays current
- public GET returns the immutable cache header and the ETag; a conditional
  request with the ETag returns 304
- public GET 404s for a draft course, for a course with no thumbnail, and
  anonymously under `coming_soon`
- deleting the course removes the object
- admin routes 401 without the session

## Acceptance
- `pytest` green; migration round-trips
- Upload artwork to `GPT` in the admin; `/courses` renders the card with it
- Hard-reload twice: the second request is served from cache, not re-fetched
- Resize to 360px: artwork on top, nothing clipped, no horizontal scroll
- Remove the artwork: the card degrades to text and stays aligned

## Do not
- Add anything to `docs/course-package.md`
- Put artwork in `frontend/public/` or `frontend/src/assets/`
- Call `touch` from either setter
- Serve the bucket directly or presign the catalog image

## When done
Append the NN entry. Under Decisions: why artwork is a business fact rather
than course content, why the route is cacheable rather than presigned, and
why the hash is in the URL. Under Known gaps: no image processing, so an
admin can upload a 4000px image that a phone downloads in full. Then stop.
