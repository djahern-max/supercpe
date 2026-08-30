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
"""

import argparse
import getpass
import io
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.constants.storage import (
    HEALTH_SENTINEL_KEY,
    MIRRORED_PREFIXES,
    OFFSITE_STAMP_KEY,
)
from app.db import SessionLocal
from app.models.account import Account
from app.services import auth as auth_service
from app.services.auth import AuthRuleViolation
from app.storage import SpacesStorage, get_storage


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

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.force)
    if args.command == "write-sentinel":
        return write_sentinel()
    if args.command == "upload-backup":
        return upload_backup(args.path)
    if args.command == "mirror-offsite":
        return mirror_offsite(args.day)
    return 1


if __name__ == "__main__":
    sys.exit(main())
