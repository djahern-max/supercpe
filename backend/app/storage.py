import mimetypes
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import ConfigurationError, settings


class Storage(Protocol):
    def put(self, key: str, fileobj: BinaryIO) -> None: ...

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def url_for(self, key: str, expires_seconds: int) -> str: ...


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"storage key escapes the storage root: {key}")
        return path

    def put(self, key: str, fileobj: BinaryIO) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as out:
            shutil.copyfileobj(fileobj, out)

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def url_for(self, key: str, expires_seconds: int) -> str:
        """A URL the player's <video> element can fetch. Local files never
        expire, so `expires_seconds` is unused; the media route plays the
        part a presigned URL plays under Spaces. Relative, so the frontend
        prefixes its API base URL."""
        return f"/api/v1/media/{key}"


class SpacesStorage:
    """DigitalOcean Spaces via its S3-compatible API. The bucket is
    private and nothing is ever served from it directly: reads go through
    the API (certificates, audits) or an expiring presigned GET (video)."""

    def __init__(
        self, bucket: str, region: str, endpoint: str, key: str, secret: str
    ):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=key,
            aws_secret_access_key=secret,
            config=BotoConfig(signature_version="s3v4"),
        )

    def put(self, key: str, fileobj: BinaryIO) -> None:
        content_type, _ = mimetypes.guess_type(key)
        # upload_fileobj goes multipart above boto3's threshold, which the
        # lesson videos need; no ACL argument, so objects stay private.
        self.client.upload_fileobj(
            fileobj,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type or "application/octet-stream"},
        )

    def open(self, key: str) -> BinaryIO:
        # botocore's StreamingBody: read() and context manager, which is
        # all any caller uses.
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def url_for(self, key: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def versioning_enabled(self) -> bool:
        """GetBucketVersioning with the runtime key (DigitalOcean grants
        it at Read permission, so the Limited Access key can ask). An
        unversioned bucket returns no Status at all; Suspended is just as
        much a failure as never-enabled."""
        response = self.client.get_bucket_versioning(Bucket=self.bucket)
        return response.get("Status") == "Enabled"


def ensure_bucket_versioning(storage: Storage) -> None:
    """Boot refusal (013): a 9.02 control that can be switched off in a
    control panel while the application keeps running normally is a
    control that will be found off during an audit. LocalStorage has
    nothing to version, so only Spaces is checked."""
    if not isinstance(storage, SpacesStorage):
        return
    if not storage.versioning_enabled():
        raise ConfigurationError(
            f"Refusing to boot: object versioning is not Enabled on "
            f"bucket '{storage.bucket}'. Run `python -m app.cli "
            "bucket-setup` with a temporary All Permissions key (see "
            "docs/OPERATIONS.md, 'Bucket versioning')."
        )


# One client per process: boto3 client construction is not cheap and
# get_storage is a per-request dependency.
_spaces: SpacesStorage | None = None


def get_storage() -> Storage:
    if settings.storage_backend == "spaces":
        global _spaces
        if _spaces is None:
            _spaces = SpacesStorage(
                settings.spaces_bucket,
                settings.spaces_region,
                settings.spaces_endpoint,
                settings.spaces_key,
                settings.spaces_secret,
            )
        return _spaces
    return LocalStorage(settings.storage_root)
