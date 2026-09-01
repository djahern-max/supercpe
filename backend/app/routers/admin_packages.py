import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.schemas.package import (
    IngestResponse,
    PackageDetail,
    PackageOverview,
    PackageSummary,
    ValidationErrors,
)
from app.services import packages
from app.services.courses import CourseRuleViolation
from app.storage import Storage, get_storage

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])


@router.post(
    "/packages",
    response_model=IngestResponse,
    status_code=201,
    responses={422: {"model": ValidationErrors}, 200: {"model": IngestResponse}},
)
def upload_package(
    file: UploadFile,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    tmp_dir = Path(tempfile.mkdtemp(prefix="supercpe-ingest-"))
    try:
        zip_path = tmp_dir / "package.zip"
        with open(zip_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        result = packages.validate(zip_path)
        if isinstance(result, list):
            return JSONResponse(status_code=422, content={"errors": result})

        package, created = packages.ingest(db, storage, result)
        response = IngestResponse(
            package=_detail(package),
            created=created,
            # An idempotent re-upload re-reports the same warnings: they
            # describe the package, not the act of uploading it.
            warnings=result.warnings,
        )
        return JSONResponse(
            status_code=201 if created else 200,
            content=response.model_dump(mode="json"),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/packages", response_model=list[PackageSummary])
def list_packages(db: Session = Depends(get_db)):
    return packages.list_packages(db)


def _detail(package) -> PackageDetail:
    """The stored row plus its derived human summary."""
    detail = PackageDetail.model_validate(package)
    detail.overview = PackageOverview(**packages.overview(package))
    return detail


@router.get("/packages/{package_id}", response_model=PackageDetail)
def get_package(package_id: int, db: Session = Depends(get_db)):
    package = packages.get_package(db, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    return _detail(package)


@router.get("/packages/{package_id}/transcript")
def get_transcript(package_id: int, db: Session = Depends(get_db)):
    package = packages.get_package(db, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    if package.transcript is None:
        # A text package has no narration to transcribe; its program
        # material is the guide, served section by section.
        raise HTTPException(
            status_code=404,
            detail="This package is a text package and has no transcript",
        )
    return PlainTextResponse(package.transcript, media_type="text/markdown")


@router.get("/packages/{package_id}/sections/{section_key}")
def get_section(
    package_id: int, section_key: str, db: Session = Depends(get_db)
):
    """One guide section's markdown as shipped — what the word count was
    taken from, and what a 4.02 reviewer reads."""
    package = packages.get_package(db, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    section = next(
        (s for s in package.sections if s.section_key == section_key), None
    )
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return PlainTextResponse(section.markdown, media_type="text/markdown")


@router.delete(
    "/packages/{package_id}",
    status_code=204,
    responses={422: {"model": ValidationErrors}},
)
def delete_package(
    package_id: int,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    try:
        deleted = packages.delete_package(db, storage, package_id)
    except CourseRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    if not deleted:
        raise HTTPException(status_code=404, detail="Package not found")
