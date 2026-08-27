from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin_packages, admin_sponsor, health, sponsor
from app.services.ffprobe import ensure_ffprobe_available


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at boot, not at first upload, if ffprobe is missing.
    ensure_ffprobe_available()
    yield


app = FastAPI(title="superCPE API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(admin_packages.router, prefix="/api/v1")
app.include_router(admin_sponsor.router, prefix="/api/v1")
app.include_router(sponsor.router, prefix="/api/v1")
