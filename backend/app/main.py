from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    admin_accounts,
    admin_audit,
    admin_courses,
    admin_enrollments,
    admin_evaluations,
    admin_packages,
    admin_smes,
    admin_sponsor,
    assessment,
    auth,
    courses,
    health,
    media,
    my,
    player,
    policies,
    review,
    site,
    sponsor,
)
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
app.include_router(auth.router, prefix="/api/v1")
app.include_router(site.router, prefix="/api/v1")
app.include_router(site.admin_router, prefix="/api/v1")
app.include_router(admin_accounts.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(admin_audit.router, prefix="/api/v1")
app.include_router(admin_courses.router, prefix="/api/v1")
app.include_router(admin_evaluations.router, prefix="/api/v1")
app.include_router(admin_enrollments.router, prefix="/api/v1")
app.include_router(admin_packages.router, prefix="/api/v1")
app.include_router(admin_smes.router, prefix="/api/v1")
app.include_router(admin_sponsor.router, prefix="/api/v1")
app.include_router(assessment.router, prefix="/api/v1")
app.include_router(assessment.admin_router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(my.router, prefix="/api/v1")
app.include_router(player.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(policies.admin_router, prefix="/api/v1")
app.include_router(sponsor.router, prefix="/api/v1")
