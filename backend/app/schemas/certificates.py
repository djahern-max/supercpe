from pydantic import BaseModel


class CertificateVerificationOut(BaseModel):
    """What the public verification page confirms (019, 9.01.1): every
    field from the completion-time snapshot, never today's course or
    sponsor rows — the certificate is the frozen fact being verified. If a
    fact is not in the snapshot, it does not appear here."""

    valid: bool
    participant_name: str
    course_title: str
    field_of_study: str
    credit: str
    # The date as printed on the certificate (item 4), not a timestamp.
    completed_at: str
    sponsor_name: str
    program_type: str
