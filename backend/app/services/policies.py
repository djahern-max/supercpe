"""The 8.01 items 8-11 policies: "formalized, published, and made
available" (8.01.1).

The three written policies are append-only versions; the current version
of a kind is derived — the latest `effective_at <= now()` — never marked.
The re-take policy is rendered from `RETAKES_ALLOWED` and `PASSING_PCT` so
it cannot disagree with what the code enforces, and the item 11 sponsor
statement renders only while `may_claim_registry` is true. A kind with no
current version is a launch blocker (`readiness.launch_findings`) and,
since 016, a publish blocker too: it fails 8.01 items 8-10 in the
disclosure completeness check, so no course can publish without it.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.assessment import PASSING_PCT, RETAKES_ALLOWED
from app.constants.certificate import NASBA_SPONSOR_STATEMENT
from app.constants.enrollment import ENROLLMENT_DAYS
from app.models.account import Account
from app.models.policy import POLICY_KINDS, PolicyVersion
from app.services import sponsor as sponsor_service

KIND_LABELS = {
    "registration": "Registration and attendance",  # 8.01 item 8
    "refund": "Refund and cancellation",  # 8.01 item 9
    "complaint": "Complaint resolution",  # 8.01 item 10
}


class PolicyRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def retake_policy_text() -> str:
    """The re-take and passing policy, from the constants that enforce it.
    6.01.2 leaves the re-take count to the sponsor; this is where the
    choice is disclosed (010 required it)."""
    return (
        f"A cumulative grade of at least {PASSING_PCT} percent on the "
        "qualified assessment is required to pass. A participant may sit "
        f"the assessment once and re-take it up to {RETAKES_ALLOWED} times "
        "per enrollment. Every sitting must be completed before the "
        f"enrollment expires, {ENROLLMENT_DAYS} days after enrollment."
    )


def versions_of(db: Session, kind: str) -> list[PolicyVersion]:
    """Every version of one kind, newest effective date first."""
    return list(
        db.scalars(
            select(PolicyVersion)
            .where(PolicyVersion.kind == kind)
            .order_by(PolicyVersion.effective_at.desc(), PolicyVersion.id.desc())
        )
    )


def current_version(db: Session, kind: str) -> PolicyVersion | None:
    """The latest version already effective. A future `effective_at` is
    not current until its moment arrives."""
    now = _now()
    return next(
        (row for row in versions_of(db, kind) if row.effective_at <= now),
        None,
    )


def missing_kinds(db: Session) -> list[str]:
    return [kind for kind in POLICY_KINDS if current_version(db, kind) is None]


def sponsor_statement(db: Session) -> str | None:
    """The 8.01 item 11 statement, or None while the sponsor may not
    claim Registry membership — the one place the gate is applied.
    Everything that renders the statement (the policies payload, the 016
    course detail) goes through here."""
    profile = sponsor_service.get_profile(db)
    if not profile.may_claim_registry:
        return None
    return NASBA_SPONSOR_STATEMENT.format(sponsor_name=profile.name)


def current(db: Session) -> dict:
    """The public /policies payload: the three kinds' current bodies, the
    derived re-take text, and — only while the sponsor may claim it — the
    item 11 statement."""
    policies = []
    for kind in POLICY_KINDS:
        version = current_version(db, kind)
        if version is not None:
            policies.append(
                {
                    "kind": kind,
                    "label": KIND_LABELS[kind],
                    "body": version.body,
                    "effective_at": version.effective_at,
                }
            )
    return {
        "policies": policies,
        "retake_policy": retake_policy_text(),
        "sponsor_statement": sponsor_statement(db),
    }


def publish(
    db: Session,
    kind: str,
    body: str,
    effective_at: datetime | None,
    account: Account,
) -> PolicyVersion:
    if kind not in POLICY_KINDS:
        raise PolicyRuleViolation(
            [f'kind must be one of {", ".join(POLICY_KINDS)}, not "{kind}"']
        )
    if not body.strip():
        raise PolicyRuleViolation(["the policy body is blank"])
    version = PolicyVersion(
        kind=kind,
        body=body,
        effective_at=effective_at or _now(),
        created_by_account_id=account.id,
    )
    db.add(version)
    db.commit()
    return version
