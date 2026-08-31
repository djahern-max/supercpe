"""Admin view of the waiting list: count, listing, soft remove, the CSV
export, and 021's invitations — the Send run and the per-row Resend.
Available in both site modes — the list closes to new entries when the
site opens, but the admin can still read and export what it collected;
only the invitation actions require `open` (the service refuses
otherwise, with the reason)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.waiting_list import WaitingListEntry
from app.schemas.package import ValidationErrors
from app.schemas.waiting_list import (
    InvitationRunOut,
    WaitingListAdminOut,
    WaitingListEntryOut,
    WaitingListRemoveRequest,
)
from app.services import invitations as invitations_service
from app.services import waiting_list as waiting_list_service
from app.services.invitations import InvitationRuleViolation

router = APIRouter(
    prefix="/admin/waiting-list",
    dependencies=[Depends(require_role("admin"))],
)


def _listing(db: Session) -> WaitingListAdminOut:
    entries = waiting_list_service.active_entries(db)
    counts = invitations_service.counts(db)
    return WaitingListAdminOut(
        total=len(entries),
        entries=[
            WaitingListEntryOut(
                id=entry.id,
                name=entry.name,
                email=entry.email,
                state=entry.state,
                firm=entry.firm,
                created_at=entry.created_at,
                source=entry.source,
                invited_at=entry.invited_at,
                invitation_status=entry.invitation_status,
            )
            for entry in entries
        ],
        invited=counts["invited"],
        failed=counts["failed"],
        invitable=counts["invitable"],
    )


@router.get("", response_model=WaitingListAdminOut)
def list_waiting_list(db: Session = Depends(get_db)):
    return _listing(db)


@router.post("/{entry_id}/remove", response_model=WaitingListAdminOut)
def remove_entry(
    entry_id: int,
    payload: WaitingListRemoveRequest,
    db: Session = Depends(get_db),
):
    entry = waiting_list_service.remove(db, entry_id, payload.reason)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such entry")
    return _listing(db)


@router.post(
    "/invitations",
    response_model=InvitationRunOut,
    responses={422: {"model": ValidationErrors}},
)
def send_invitations(db: Session = Depends(get_db)):
    """021: the Send button. Refuses while coming_soon (the links would
    404); otherwise sends to every invitable entry sequentially and
    returns the run summary. Idempotent — re-running skips every `sent`
    row, which makes this same button the retry after a partial
    failure. Each send is logged as every send is (`email_message`),
    and the run summary goes to the app log."""
    try:
        return invitations_service.send_all(db)
    except InvitationRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})


@router.post(
    "/{entry_id}/resend",
    response_model=WaitingListAdminOut,
    responses={422: {"model": ValidationErrors}},
)
def resend_invitation(entry_id: int, db: Session = Depends(get_db)):
    """021: the per-row button behind a `failed` row, for symmetry with
    019's certificate Resend. Same rules as the run — never a removed
    entry, never a second successful invitation, never while
    coming_soon."""
    entry = db.get(WaitingListEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such entry")
    try:
        invitations_service.resend(db, entry)
    except InvitationRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return _listing(db)


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    # A download generated on request: not written to Spaces, not part of
    # the 9.02 audit bundle — these rows are not CPE records.
    return Response(
        content=waiting_list_service.export_csv(db),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="waiting-list.csv"'
        },
    )
