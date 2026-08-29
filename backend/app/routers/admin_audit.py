"""The per-course audit bundle export (9.02.2), generated and logged."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.models.audit import AuditExport
from app.models.course import Course
from app.schemas.audit import AuditBundleRequest, AuditExportOut
from app.services import audit_bundle, courses
from app.storage import Storage, get_storage

router = APIRouter(
    prefix="/admin/courses", dependencies=[Depends(require_role("admin"))]
)


def _get_course_or_404(db: Session, course_code: str) -> Course:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _export_out(export: AuditExport) -> AuditExportOut:
    return AuditExportOut(
        id=export.id,
        generated_at=export.generated_at,
        generated_by_email=export.generated_by.email,
        sha256=export.sha256,
        size_bytes=export.size_bytes,
        storage_key=export.storage_key,
    )


@router.post(
    "/{course_code}/audit-bundle",
    response_model=AuditExportOut,
    status_code=201,
)
def generate_bundle(
    course_code: str,
    payload: AuditBundleRequest,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
    account: Account = Depends(require_role("admin")),
):
    course = _get_course_or_404(db, course_code)
    export = audit_bundle.create_export(
        db, storage, course, account, payload.include_video
    )
    return _export_out(export)


@router.get(
    "/{course_code}/audit-bundle", response_model=list[AuditExportOut]
)
def list_bundles(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    return [
        _export_out(export)
        for export in audit_bundle.list_exports(db, course)
    ]


@router.get("/{course_code}/audit-bundle/{export_id}.zip")
def download_bundle(
    course_code: str,
    export_id: int,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    course = _get_course_or_404(db, course_code)
    export = db.get(AuditExport, export_id)
    if export is None or export.course_id != course.id:
        raise HTTPException(status_code=404, detail="Export not found")
    with storage.open(export.storage_key) as archive:
        content = archive.read()
    filename = export.storage_key.rsplit("/", 1)[-1]
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{course.course_code}-audit-{filename}"'
            )
        },
    )
