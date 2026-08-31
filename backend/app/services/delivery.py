"""Certificate delivery by email (019): a courtesy layered on the record.

The completion snapshot and its stored PDF are the 9.01 documentation, and
the participant's own download from their account is what satisfies the
60-day timeliness expectation; what this module adds is satisfying it
without being asked — one email at completion, kind `certificate`, the
PDF attached. The rule that shapes everything here: **delivery failure
cannot fail completion**. `deliver_after_completion` runs only after the
passing submit's transaction has committed, and every failure is recorded
on the row (`delivery_status`), never raised.

No automatic retries: a `failed` status is the loud flag on the admin
completions view, and the admin Resend button (`send_certificate` again)
is the whole recovery path.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.enrollment import Completion
from app.services import completions
from app.services import email as email_service
from app.services.completions import IssuanceBlocked
from app.storage import Storage

logger = logging.getLogger("app.delivery")


def _site_origin() -> str:
    # Same reasoning as 017's registration links: in prod CORS_ORIGINS is
    # exactly https://supercpe.com; in dev the first origin is where the
    # frontend lives.
    return settings.cors_origins_list[0]


def send_certificate(
    db: Session, storage: Storage, completion: Completion
) -> Completion:
    """Render if needed, send the one certificate email, and record the
    outcome. Raises IssuanceBlocked while the sponsor's fields still block
    the render — there is nothing to send yet, so delivery stays pending.
    A refused send is recorded as `failed`, never raised."""
    completions.ensure_rendered(db, storage, completion)
    account = completion.enrollment.account
    snapshot = completion.certificate_snapshot
    sponsor = snapshot["sponsor_name"]
    filename = f"certificate-{completion.certificate_number}.pdf"
    with storage.open(completion.certificate_key) as pdf:
        content = pdf.read()
    subject = f"Your CPE certificate from {sponsor}"
    body = (
        f"Hello {snapshot['participant_name'] or account.email},\n\n"
        f"You completed {snapshot['course_title']} on "
        f"{snapshot['completed_at'][:10]} and earned {snapshot['credit']} "
        f"CPE credit in {snapshot['field_of_study']}. Your certificate is "
        f"attached.\n\n"
        f"Your certificates are always available from your account:\n\n"
        f"{_site_origin()}/my/courses\n\n"
        f"— {sponsor}"
    )
    try:
        email_service.send(
            db,
            "certificate",
            account.email,
            subject,
            body,
            attachment=(filename, content),
        )
    except Exception:
        logger.exception(
            "certificate %s: the email backend refused the send",
            completion.certificate_number,
        )
        completion.delivery_status = "failed"
        completion.delivered_at = None
        db.commit()
        return completion
    completion.delivery_status = "sent"
    completion.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return completion


def deliver_after_completion(
    db: Session, storage: Storage, completion: Completion
) -> None:
    """The completion-time send. Called strictly after the passing submit
    committed — a certificate email about a completion that then rolled
    back would be a lie in someone's inbox — and swallows everything:
    nothing in delivery may add a failure mode to completion."""
    try:
        send_certificate(db, storage, completion)
    except IssuanceBlocked:
        # The 010 render gate refused; delivery stays pending and the
        # admin sponsor view already reports which fields are missing.
        logger.info(
            "certificate %s awaits issuance; delivery stays pending",
            completion.certificate_number,
        )
    except Exception:
        # A render or storage failure, not a send refusal (send_certificate
        # records those itself). Record it the same way, defensively.
        logger.exception(
            "certificate %s could not be delivered",
            completion.certificate_number,
        )
        try:
            db.rollback()
            completion.delivery_status = "failed"
            completion.delivered_at = None
            db.commit()
        except Exception:
            logger.exception(
                "certificate %s: the failed delivery could not be recorded",
                completion.certificate_number,
            )
