"""Command-line entry points.

    python -m app.cli create-admin --email you@example.com

creates the first admin account. The password is prompted, never a flag —
a flag would land in shell history. The created admin does not have to
change it (they chose it themselves); admin-created accounts do.

    python -m app.cli write-sentinel

writes the health/sentinel object the health endpoint checks (run once at
first deploy).

    python -m app.cli upload-backup /backups/2026-08-29.dump.gz

uploads a nightly dump to backups/, stamps backups/LATEST, and prunes to
the retention policy. Called by deploy/backup.sh, Spaces-only.

    python -m app.cli mirror-offsite 2026-08-30

mirrors that night's dump plus certificates/ and audits/ to the off-site
bucket, then stamps backups/OFFSITE in the primary. Called by
deploy/backup.sh after upload-backup, so an off-site failure exits
non-zero without ever leaving backups/LATEST unstamped.

    SETUP_SPACES_KEY=... SETUP_SPACES_SECRET=... python -m app.cli bucket-setup

enables object versioning and the backups/ lifecycle rule on the bucket
(013, moved here from deploy/bucket-setup.py by 014a so it runs inside
the api image with no host Python and no mounts). Credentials come only
from those two variables — a temporary All Permissions Spaces key,
never .env, deleted after the read-backs print.

    python -m app.cli preflight

runs, without starting the server, exactly the checks that would refuse
boot in prod. deploy.sh runs it from the newly built image before
migrations, so a boot refusal becomes a failed deploy with the old
version still serving, never an outage (014a).
"""

import argparse
import getpass
import io
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select

from app.config import SPACES_VARS, ConfigurationError, boot_violations, settings
from app.constants.storage import (
    BACKUP_NONCURRENT_DAYS,
    BACKUPS_PREFIX,
    HEALTH_SENTINEL_KEY,
    MIRRORED_PREFIXES,
    OFFSITE_STAMP_KEY,
)
from app.db import SessionLocal
from app.models.account import Account
from app.services import auth as auth_service
from app.services.auth import AuthRuleViolation
from app.services.ffprobe import FfprobeNotFoundError, ensure_ffprobe_available
from app.storage import SpacesStorage, ensure_bucket_versioning, get_storage


def create_admin(email: str, force: bool) -> int:
    db = SessionLocal()
    try:
        existing = db.scalars(
            select(Account).where(Account.role == "admin")
        ).all()
        if existing and not force:
            print(
                f"An admin already exists ({existing[0].email}). "
                "Create further accounts from /admin/accounts, or pass "
                "--force to add another admin from here.",
                file=sys.stderr,
            )
            return 1

        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("The passwords do not match.", file=sys.stderr)
            return 1

        try:
            account = auth_service.create_account(
                db,
                email,
                "admin",
                password,
                created_by=None,
                must_change_password=False,
            )
        except AuthRuleViolation as violation:
            for error in violation.errors:
                print(error, file=sys.stderr)
            return 1

        print(f"Created admin {account.email} (account id {account.id}).")
        return 0
    finally:
        db.close()


def write_sentinel() -> int:
    storage = get_storage()
    storage.put(HEALTH_SENTINEL_KEY, io.BytesIO(b"ok"))
    print(f"Wrote {HEALTH_SENTINEL_KEY}.")
    return 0


def upload_backup(path: str) -> int:
    from app.services import backups

    storage = get_storage()
    if not isinstance(storage, SpacesStorage):
        print(
            "upload-backup requires STORAGE_BACKEND=spaces: a backup on "
            "the same disk as the database is not retention (9.02).",
            file=sys.stderr,
        )
        return 1
    try:
        key = backups.upload(storage, Path(path))
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Uploaded {key} and updated backups/LATEST.")
    return 0


def mirror_offsite(day_text: str | None) -> int:
    from botocore.exceptions import BotoCoreError, ClientError

    from app.services import offsite as offsite_service

    storage = get_storage()
    if not isinstance(storage, SpacesStorage):
        print(
            "mirror-offsite requires STORAGE_BACKEND=spaces: there is no "
            "primary bucket to mirror from.",
            file=sys.stderr,
        )
        return 1
    offsite = offsite_service.get_offsite()
    if offsite is None:
        # Not a failure: the missing-offsite state is reported by /health
        # (last_offsite_backup_at: null), not refused, so an unconfigured
        # night must not make the backup cron look broken.
        print("OFFSITE_* is not configured; nothing mirrored.")
        return 0
    day = date.fromisoformat(day_text) if day_text else datetime.now(timezone.utc).date()
    try:
        key = offsite_service.mirror_backup(storage, offsite, day)
        copied = {
            prefix: offsite_service.mirror_prefix(storage, offsite, prefix)
            for prefix in MIRRORED_PREFIXES
        }
    except (BotoCoreError, ClientError, OSError) as error:
        print(f"off-site mirror failed: {error}", file=sys.stderr)
        return 1
    stamp = datetime.now(timezone.utc).isoformat()
    storage.put(OFFSITE_STAMP_KEY, io.BytesIO(f"{stamp}\n".encode()))
    mirrored = ", ".join(f"{count} under {prefix}" for prefix, count in copied.items())
    print(f"Mirrored {key} off-site ({mirrored}) and stamped {OFFSITE_STAMP_KEY}.")
    return 0


RULE_ID = "expire-noncurrent-backup-versions"

LIFECYCLE = {
    "Rules": [
        {
            "ID": RULE_ID,
            "Status": "Enabled",
            "Filter": {"Prefix": BACKUPS_PREFIX},
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": BACKUP_NONCURRENT_DAYS
            },
        }
    ]
}

ACCESS_DENIED_HINT = (
    "AccessDenied on a bucket-configuration call. A bucket-scoped Spaces "
    "key cannot perform bucket-configuration operations (PutBucketVersioning, "
    "lifecycle) even with full object permissions. Create a temporary "
    "All Permissions (all buckets) key in the DigitalOcean console — "
    "Spaces Object Storage → Access Keys — re-run, then delete it."
)


def rule_prefix(rule: dict) -> str | None:
    """S3 lifecycle has two shapes for the same thing: the current
    Filter.Prefix and the legacy top-level Prefix. Some S3-compatible
    stores read one back as the other; either counts."""
    if "Filter" in rule:
        return rule["Filter"].get("Prefix")
    return rule.get("Prefix")


def run_bucket_setup(client, bucket: str) -> int:
    """Enable versioning and the one backups/ lifecycle rule, read both
    back, exit non-zero if either does not read back as set. Idempotent —
    running it twice changes nothing and reports the same. Every other
    prefix (packages/, certificates/, audits/) is 9.02 material and is
    never expired — no rule touches it."""
    try:
        client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )
        client.put_bucket_lifecycle_configuration(
            Bucket=bucket, LifecycleConfiguration=LIFECYCLE
        )

        failures = []

        status = client.get_bucket_versioning(Bucket=bucket).get("Status")
        print(f"versioning: {status}")
        if status != "Enabled":
            failures.append(f"versioning read back as {status!r}, not 'Enabled'")

        try:
            rules = client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
        except (BotoCoreError, ClientError, KeyError) as error:
            rules = []
            failures.append(f"lifecycle configuration did not read back: {error}")
        print("lifecycle:", json.dumps(rules, indent=2, default=str))
    except ClientError as error:
        if error.response["Error"]["Code"] == "AccessDenied":
            print(ACCESS_DENIED_HINT, file=sys.stderr)
            return 1
        raise
    if rules:
        if len(rules) != 1:
            failures.append(f"expected exactly one lifecycle rule, read {len(rules)}")
        rule = rules[0]
        if rule.get("Status") != "Enabled":
            failures.append("the lifecycle rule read back as not Enabled")
        if rule_prefix(rule) != BACKUPS_PREFIX:
            failures.append(
                f"the rule's prefix read back as {rule_prefix(rule)!r}, "
                f"not {BACKUPS_PREFIX!r}"
            )
        days = rule.get("NoncurrentVersionExpiration", {}).get("NoncurrentDays")
        if days != BACKUP_NONCURRENT_DAYS:
            failures.append(
                f"NoncurrentDays read back as {days!r}, not "
                f"{BACKUP_NONCURRENT_DAYS}"
            )
        extra = set(rule) - {
            "ID", "Status", "Filter", "Prefix", "NoncurrentVersionExpiration"
        }
        if extra:
            failures.append(f"the rule carries unexpected actions: {sorted(extra)}")

    if failures:
        print("FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("ok: versioning Enabled, one lifecycle rule on backups/ "
          f"({BACKUP_NONCURRENT_DAYS} noncurrent days).")
    return 0


def bucket_setup() -> int:
    key = os.environ.get("SETUP_SPACES_KEY")
    secret = os.environ.get("SETUP_SPACES_SECRET")
    if not key or not secret:
        print(
            "SETUP_SPACES_KEY and SETUP_SPACES_SECRET must be set in the "
            "environment (a temporary All Permissions key; never put it "
            "in .env).",
            file=sys.stderr,
        )
        return 2
    if not (
        settings.spaces_bucket and settings.spaces_region and settings.spaces_endpoint
    ):
        print(
            "SPACES_BUCKET, SPACES_REGION, and SPACES_ENDPOINT must be set "
            "(the container's env file provides them in production).",
            file=sys.stderr,
        )
        return 2
    client = boto3.client(
        "s3",
        region_name=settings.spaces_region,
        endpoint_url=settings.spaces_endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=BotoConfig(signature_version="s3v4"),
    )
    return run_bucket_setup(client, settings.spaces_bucket)


def preflight() -> int:
    """Every check that would refuse boot, without booting: the 012
    config validations (same code path, every violation at once), the
    013 versioning guard, and the 002 ffprobe requirement."""
    violations = boot_violations(settings)
    spaces_configured = settings.storage_backend == "spaces" and all(
        getattr(settings, var.lower()) for var in SPACES_VARS
    )
    if spaces_configured:
        try:
            ensure_bucket_versioning(get_storage())
        except ConfigurationError as error:
            violations.append(str(error))
        except (BotoCoreError, ClientError) as error:
            violations.append(
                "bucket_versioning could not be verified on bucket "
                f"'{settings.spaces_bucket}': {error}"
            )
    try:
        ensure_ffprobe_available()
    except FfprobeNotFoundError as error:
        violations.append(str(error))

    if violations:
        print("preflight FAILED — the app would refuse to boot:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("preflight ok: the app would boot with this configuration.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-admin", help="Create an admin account (prompts for a password)"
    )
    create.add_argument("--email", required=True)
    create.add_argument(
        "--force",
        action="store_true",
        help="Create the admin even though one already exists",
    )

    subparsers.add_parser(
        "write-sentinel", help="Write the health/sentinel storage object"
    )

    backup = subparsers.add_parser(
        "upload-backup",
        help="Upload a pg_dump to backups/ and prune old ones",
    )
    backup.add_argument("path")

    mirror = subparsers.add_parser(
        "mirror-offsite",
        help="Mirror tonight's dump, certificates/, and audits/ off-site",
    )
    mirror.add_argument(
        "day",
        nargs="?",
        help="Dump date as YYYY-MM-DD (default: today, UTC)",
    )

    subparsers.add_parser(
        "bucket-setup",
        help="Enable bucket versioning + the backups/ lifecycle rule "
        "(needs SETUP_SPACES_KEY/SETUP_SPACES_SECRET)",
    )

    subparsers.add_parser(
        "preflight",
        help="Run every boot refusal without booting; non-zero means "
        "the app would not start",
    )

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.force)
    if args.command == "write-sentinel":
        return write_sentinel()
    if args.command == "upload-backup":
        return upload_backup(args.path)
    if args.command == "mirror-offsite":
        return mirror_offsite(args.day)
    if args.command == "bucket-setup":
        return bucket_setup()
    if args.command == "preflight":
        return preflight()
    return 1


if __name__ == "__main__":
    sys.exit(main())
