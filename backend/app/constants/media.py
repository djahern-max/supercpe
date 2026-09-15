"""Catalog artwork limits (035). Every number here is ours, not NASBA's.

8.01's list of what a sponsor must make available in advance has eleven
items (printed page 20) and a picture is not one of them, so nothing in
this file is traceable to a paragraph. The limits exist because an
unbounded upload on an anonymous marketing page is a bandwidth bill and
a bad phone experience, not because a Standard says so.

The allowed types are the three the browsers a CPA uses all decode
without a plugin. The type is decided by the file's own magic bytes, not
by the multipart `content-type` header the browser guessed from the
extension.
"""

# Magic-byte prefix -> the extension the stored key gets and the media
# type the public route answers with. WebP is a RIFF container, so its
# signature is split across bytes 0-3 and 8-11 and is checked separately
# in services.courses.
THUMBNAIL_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

# Two megabytes is generous for a 16:9 catalog card and still small
# enough that a stray full-resolution export is refused rather than
# downloaded by every visitor. Same cap as the certificate mark (032).
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024

# Nothing is resized server-side (a stated non-goal), so the edges are a
# refusal, not a transformation. Below 600px the artwork is soft on a
# 2x phone screen at the card's 240px column; above 4000px the file is
# a print export that no visitor needs.
THUMBNAIL_MIN_EDGE = 600
THUMBNAIL_MAX_EDGE = 4000

# `course-thumbnails/<course_code>/<sha256>.<ext>`. Deliberately not in
# storage.MIRRORED_PREFIXES: the off-site mirror carries 9.02 material,
# and marketing artwork is evidence of nothing.
THUMBNAIL_KEY_PREFIX = "course-thumbnails"

# How long the public route tells browsers and any CDN in front of it to
# keep the bytes. Safe at a year because the URL carries the content
# hash: a replacement is a different URL, never a stale hit.
THUMBNAIL_CACHE_SECONDS = 31536000
