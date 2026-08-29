"""Command-line entry points.

    python -m app.cli create-admin --email you@example.com

creates the first admin account. The password is prompted, never a flag —
a flag would land in shell history. The created admin does not have to
change it (they chose it themselves); admin-created accounts do.
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.account import Account
from app.services import auth as auth_service
from app.services.auth import AuthRuleViolation


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

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.force)
    return 1


if __name__ == "__main__":
    sys.exit(main())
