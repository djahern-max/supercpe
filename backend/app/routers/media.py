"""Serves LocalStorage objects to the player's <video> element.

The local stand-in for a presigned Spaces URL (012): a <video> element
cannot send the admin token header, and a presigned URL carries no auth
either. Only ever referenced by URLs `LocalStorage.url_for` hands out;
`SpacesStorage.url_for` returns absolute presigned URLs and never routes
here. Mounted only when STORAGE_BACKEND=local (see app/main.py); the
isinstance guard below is defense in depth for tests that override
`get_storage`.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.storage import LocalStorage, Storage, get_storage

router = APIRouter(prefix="/media")


@router.get("/{key:path}")
def get_media(key: str, storage: Storage = Depends(get_storage)):
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        path = storage._path(key)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    # FileResponse honors Range requests, which <video> seeking needs.
    return FileResponse(path)
