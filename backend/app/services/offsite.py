"""Off-site mirror of the retained records (9.02: a record that exists at
completion must still exist five years later even if the provider is
lost). Everything at DigitalOcean — originals, snapshots, nightly dumps —
shares one account, one region, one bill; this module copies the nightly
dump and the small retained prefixes (`certificates/`, the 9.01 evidence
of completion; `audits/`, the 9.02.2 documentation set) to a second
S3-compatible bucket at a different provider.

Called by `python -m app.cli mirror-offsite` from deploy/backup.sh after
the primary upload has already stamped backups/LATEST, so a dead off-site
provider can never make last_backup_at stale and mask the primary as the
problem. Nothing here ever deletes anything off-site.
"""

import mimetypes
from datetime import date

from botocore.exceptions import ClientError

from app.config import settings
from app.constants.storage import BACKUP_LATEST_KEY, BACKUPS_PREFIX
from app.storage import SpacesStorage

# Multipart uploads have composite ETags that differ between providers,
# so idempotence cannot compare the two buckets' own ETags. Instead every
# mirrored object carries the primary ETag it was copied from as
# metadata, and a re-run copies only when the primary ETag has moved.
SOURCE_ETAG_META = "source-etag"


def get_offsite() -> SpacesStorage | None:
    """The off-site client, or None while OFFSITE_* is unconfigured
    (boot already refused a partial configuration)."""
    if not settings.offsite_configured:
        return None
    return SpacesStorage(
        settings.offsite_bucket,
        settings.offsite_region,
        settings.offsite_endpoint,
        settings.offsite_key,
        settings.offsite_secret,
    )


def mirror_backup(primary: SpacesStorage, offsite: SpacesStorage, day: date) -> str:
    """Copies one night's dump off-site and stamps backups/LATEST there
    with the primary's own LATEST content, so the two buckets agree on
    what the newest dump is. Returns the mirrored key."""
    key = f"{BACKUPS_PREFIX}{day.isoformat()}.dump.gz"
    _copy(primary, offsite, key)
    with primary.open(BACKUP_LATEST_KEY) as latest:
        offsite.client.put_object(
            Bucket=offsite.bucket, Key=BACKUP_LATEST_KEY, Body=latest.read()
        )
    return key


def mirror_prefix(primary: SpacesStorage, offsite: SpacesStorage, prefix: str) -> int:
    """Copies every object under `prefix` that is absent off-site or
    whose primary ETag differs from the one recorded at the last copy.
    Never deletes. Returns how many objects were copied."""
    copied = 0
    paginator = primary.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=primary.bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            etag = obj["ETag"].strip('"')
            if _offsite_etag(offsite, obj["Key"]) != etag:
                _copy(primary, offsite, obj["Key"], etag)
                copied += 1
    return copied


def _offsite_etag(offsite: SpacesStorage, key: str) -> str | None:
    """The primary ETag recorded on the off-site copy, or None when the
    object is absent off-site (or predates the metadata, which forces one
    harmless re-copy)."""
    try:
        head = offsite.client.head_object(Bucket=offsite.bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise
    return head.get("Metadata", {}).get(SOURCE_ETAG_META)


def _copy(
    primary: SpacesStorage,
    offsite: SpacesStorage,
    key: str,
    source_etag: str | None = None,
) -> None:
    if source_etag is None:
        head = primary.client.head_object(Bucket=primary.bucket, Key=key)
        source_etag = head["ETag"].strip('"')
    content_type, _ = mimetypes.guess_type(key)
    # put_object, not upload_fileobj: a single-part put keeps the copy
    # one atomic write. The mirrored objects are dumps, PDFs, and bundle
    # zips — all far below put_object's 5 GB ceiling.
    with primary.open(key) as body:
        offsite.client.put_object(
            Bucket=offsite.bucket,
            Key=key,
            Body=body.read(),
            ContentType=content_type or "application/octet-stream",
            Metadata={SOURCE_ETAG_META: source_etag},
        )
