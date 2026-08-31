"""Waiting-list invitations (021): the one email the list was promised.

Everyone who signed the 015 coming-soon form was told they would hear
once when the site opened. This module keeps that promise — one
invitation per entry, ever — with 019's shape: a per-row status flag, no
retry machinery, and a human button as the whole recovery path.

The rules that shape everything here:

- **Refuse while `coming_soon`.** The invitation links to the register
  and course pages, which 404 until the site is open — inviting people
  to a gated site would 404 in their faces. Keeping the send impossible
  until `open` also means the flip can be rehearsed without a mass email
  riding on it. The flip itself never sends; this action is deliberately
  separate.
- **Idempotent by construction.** A `sent` row is skipped by every later
  run, so the batch button re-run is the retry for `failed` rows and the
  crash recovery both. Sends go one row at a time with a per-row commit,
  so a crash mid-run loses nothing already recorded.
- **The email discloses nothing.** One plain sentence names the course;
  the links carry the reader to the register page and to the course page
  where the full 8.01 disclosure lives. No credit figure, no field of
  study, no level, no price, no "National Registry" — the same restraint
  as the 015 landing page, for the same reason (partial disclosure reads
  as descriptive material).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.waiting_list import WaitingListEntry
from app.services import courses as courses_service
from app.services import email as email_service
from app.services import site as site_service
from app.services import waiting_list as waiting_list_service
from app.services.sponsor import get_profile

logger = logging.getLogger("app.invitations")


class InvitationRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_invitable(entry: WaitingListEntry) -> bool:
    """Active and never successfully invited. A `failed` row stays
    invitable; a `sent` row never is again — one invitation per entry,
    ever."""
    return entry.removed_at is None and entry.invitation_status != "sent"


def counts(db: Session) -> dict:
    """The Invitations panel's numbers, over active entries only —
    removed rows leave every count, as everywhere on this list."""
    entries = waiting_list_service.active_entries(db)
    return {
        "active": len(entries),
        "invited": sum(1 for e in entries if e.invitation_status == "sent"),
        "failed": sum(1 for e in entries if e.invitation_status == "failed"),
        "invitable": sum(1 for e in entries if is_invitable(e)),
    }


def _course_to_name(db: Session) -> Course:
    """The course the invitation names and links: the published catalog's
    first course. The open gate guaranteed one at the flip; this refusal
    only fires if everything was unpublished afterwards — there would be
    no page to link."""
    published = courses_service.list_published(db)
    if not published:
        raise InvitationRuleViolation(
            [
                "No course is published, so there is no course page to "
                "link. Publish the course before sending invitations."
            ]
        )
    return published[0]


def _check_site_open(db: Session) -> None:
    if site_service.get_site_mode(db) != "open":
        raise InvitationRuleViolation(
            [
                "The site is still coming_soon, so nothing was sent: the "
                "invitation links people to the register and course "
                "pages, which 404 until the site is open. Open the site "
                "first — the flip itself never sends invitations; this "
                "button stays a separate, deliberate step."
            ]
        )


def render_invitation(
    name: str, course: Course, sponsor_name: str
) -> tuple[str, str]:
    """The one message, as (subject, body). Deliberately bare: the naming
    sentence is the only course fact, both links point at pages that say
    the rest (the course page carries the full 8.01 disclosure), and the
    closing line keeps the 015 promise explicit. No Registry sentence,
    claimable or not — the site says what may be said."""
    # 022 lifted the origin helper to the site service for the sitemap.
    origin = site_service.site_origin()
    subject = f"{sponsor_name} is open"
    body = (
        f"Hello {name},\n\n"
        f"You asked to hear when {sponsor_name} opened, and it is open "
        f"now. The first course is {course.title}; everything about it "
        f"is on the course page:\n\n"
        f"{origin}/courses/{course.course_code}\n\n"
        f"To take it, start by creating an account:\n\n"
        f"{origin}/register\n\n"
        f"You asked to be told once, and this is that one email — "
        f"{sponsor_name} will not email you again. If you register, "
        f"your account has its own transactional email, like "
        f"verification and certificates.\n\n"
        f"— {sponsor_name}"
    )
    return subject, body


def _send_one(
    db: Session, entry: WaitingListEntry, course: Course, sponsor_name: str
) -> bool:
    """One row, one commit. The status is staged before the send so that
    `email_service.send`'s own commit records the message row and the
    `sent` flag together — a crash between them cannot leave an email
    delivered but unrecorded. A refused send rolls that back and commits
    `failed` instead; it is recorded, never raised."""
    subject, body = render_invitation(entry.name, course, sponsor_name)
    entry.invitation_status = "sent"
    entry.invited_at = _now()
    try:
        email_service.send(db, "invitation", entry.email, subject, body)
    except Exception:
        logger.exception(
            "invitation to %s: the email backend refused the send",
            entry.email,
        )
        db.rollback()
        entry.invitation_status = "failed"
        entry.invited_at = _now()
        db.commit()
        return False
    return True


def send_all(db: Session) -> dict:
    """The Send button: every invitable entry, sequentially, one failure
    never stopping the run. Re-running skips every `sent` row, so this
    same button is the retry after a partial failure."""
    _check_site_open(db)
    course = _course_to_name(db)
    sponsor_name = get_profile(db).name
    sent = failed = skipped = 0
    for entry in waiting_list_service.active_entries(db):
        if entry.invitation_status == "sent":
            skipped += 1
            continue
        if _send_one(db, entry, course, sponsor_name):
            sent += 1
        else:
            failed += 1
    summary = {
        "attempted": sent + failed,
        "sent": sent,
        "failed": failed,
        "skipped_already_invited": skipped,
    }
    logger.info(
        "invitation run: attempted %(attempted)s, sent %(sent)s, failed "
        "%(failed)s, skipped %(skipped_already_invited)s already invited",
        summary,
    )
    return summary


def resend(db: Session, entry: WaitingListEntry) -> WaitingListEntry:
    """The per-row button, for symmetry with 019's certificate Resend.
    Same rules as the run: never a removed entry, never a second
    successful invitation, never while coming_soon."""
    _check_site_open(db)
    if entry.removed_at is not None:
        raise InvitationRuleViolation(
            ["This entry was removed from the list and is never invited."]
        )
    if entry.invitation_status == "sent":
        raise InvitationRuleViolation(
            [
                "This entry was already invited; the promise is one "
                "email, ever."
            ]
        )
    course = _course_to_name(db)
    _send_one(db, entry, course, get_profile(db).name)
    return entry
