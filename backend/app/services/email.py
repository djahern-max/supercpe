"""Outbound email (017): one interface, two backends chosen by config.

`send` is the whole interface — 019's certificates and 021's invitations
call it too; they do not get their own senders. The backend comes from
`EMAIL_BACKEND`:

- console (dev and every test): the full message goes to the log; nothing
  touches the network.
- smtp (production): generic SMTP with STARTTLS from the EMAIL_* values.
  Provider-agnostic on purpose — choosing a provider is an ops step
  recorded in docs/OPERATIONS.md, not a code change.

Every send writes one `email_message` row — kind, recipient, subject,
backend, never the body (a verification link at rest belongs only in the
token table, hashed). The row is written after the backend accepts the
message, so the log records what was handed off, not what was attempted.
A send failure propagates: every branch of a constant-response route
sends, so an SMTP outage fails them all alike and reveals nothing.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

from sqlalchemy.orm import Session

from app.config import settings
from app.models.email_message import EmailMessage

logger = logging.getLogger("app.email")


def send(
    db: Session, kind: str, recipient: str, subject: str, body: str
) -> EmailMessage:
    backend = settings.email_backend
    if backend == "smtp":
        _smtp_send(recipient, subject, body)
    else:
        logger.info(
            "console email backend\nKind: %s\nTo: %s\nSubject: %s\n\n%s",
            kind,
            recipient,
            subject,
            body,
        )
    message = EmailMessage(
        kind=kind, recipient=recipient, subject=subject, backend=backend
    )
    db.add(message)
    db.commit()
    return message


def _smtp_send(recipient: str, subject: str, body: str) -> None:
    message = MimeMessage()
    message["From"] = settings.email_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(
        settings.email_host, settings.email_port, timeout=30
    ) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.email_username, settings.email_password)
        smtp.send_message(message)
