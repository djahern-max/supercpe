#!/usr/bin/env python3
"""Enable object versioning and the backups/ lifecycle rule on the
production bucket (013). Run once, by hand, from the laptop's backend
venv (it only makes remote API calls; boto3 is already there):

    cd backend && source .venv/bin/activate && cd ..
    SETUP_SPACES_KEY=... SETUP_SPACES_SECRET=... \
        python deploy/bucket-setup.py supercpe-prod-nyc3

The credentials are a TEMPORARY Full Access Spaces key (the runtime
Limited Access key cannot change versioning or lifecycle), passed only as
environment variables, never read from any .env, and deleted in the
acceptance walkthrough after this script succeeds.

What it does, idempotently — running it twice changes nothing and
reports the same:

- Enables object versioning on the bucket, so an accidental overwrite or
  delete of a retained object (9.02) keeps every prior version.
- Puts a lifecycle configuration with exactly one rule: expire noncurrent
  versions under backups/ after BACKUP_NONCURRENT_DAYS. Every other
  prefix (packages/, certificates/, audits/) is 9.02 material and is
  never expired — no rule touches it.
- Reads both back and exits non-zero if either does not read back as
  set. That read-back against the real bucket is the proof DigitalOcean
  honored the configuration.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.constants.storage import BACKUP_NONCURRENT_DAYS, BACKUPS_PREFIX  # noqa: E402

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


def rule_prefix(rule: dict) -> str | None:
    """S3 lifecycle has two shapes for the same thing: the current
    Filter.Prefix and the legacy top-level Prefix. Some S3-compatible
    stores read one back as the other; either counts."""
    if "Filter" in rule:
        return rule["Filter"].get("Prefix")
    return rule.get("Prefix")


def setup(client, bucket: str) -> int:
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
    except Exception as error:
        rules = []
        failures.append(f"lifecycle configuration did not read back: {error}")
    print("lifecycle:", json.dumps(rules, indent=2, default=str))
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable versioning + the backups/ lifecycle rule (Full Access key)"
    )
    parser.add_argument("bucket")
    parser.add_argument("--region", default="nyc3")
    parser.add_argument("--endpoint", default="https://nyc3.digitaloceanspaces.com")
    args = parser.parse_args()

    key = os.environ.get("SETUP_SPACES_KEY")
    secret = os.environ.get("SETUP_SPACES_SECRET")
    if not key or not secret:
        print(
            "SETUP_SPACES_KEY and SETUP_SPACES_SECRET must be set in the "
            "environment (a temporary Full Access key; never put it in .env).",
            file=sys.stderr,
        )
        return 2

    client = boto3.client(
        "s3",
        region_name=args.region,
        endpoint_url=args.endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=BotoConfig(signature_version="s3v4"),
    )
    return setup(client, args.bucket)


if __name__ == "__main__":
    sys.exit(main())
