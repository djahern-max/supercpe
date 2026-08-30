"""Admin view of the waiting list: count, listing, soft remove, and the
CSV export that will feed 021's invitations. Available in both site
modes — the list closes to new entries when the site opens, but the
admin can still read and export what it collected."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.schemas.waiting_list import (
    WaitingListAdminOut,
    WaitingListEntryOut,
    WaitingListRemoveRequest,
)
from app.services import waiting_list as waiting_list_service

router = APIRouter(
    prefix="/admin/waiting-list",
    dependencies=[Depends(require_role("admin"))],
)


def _listing(db: Session) -> WaitingListAdminOut:
    entries = waiting_list_service.active_entries(db)
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
            )
            for entry in entries
        ],
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
