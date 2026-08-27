import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.schemas.package import (
    IngestResponse,
    PackageDetail,
    PackageSummary,
    ValidationErrors,
)
from app.services import packages
from app.storage import Storage, get_storage

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


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
            package=PackageDetail.model_validate(package), created=created
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


@router.get("/packages/{package_id}", response_model=PackageDetail)
def get_package(package_id: int, db: Session = Depends(get_db)):
    package = packages.get_package(db, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@router.get("/packages/{package_id}/transcript")
def get_transcript(package_id: int, db: Session = Depends(get_db)):
    package = packages.get_package(db, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    return PlainTextResponse(package.transcript, media_type="text/markdown")
