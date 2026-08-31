from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ensure_boot_config, settings
from app.routers import (
    admin_accounts,
    admin_audit,
    admin_courses,
    admin_enrollments,
    admin_evaluations,
    admin_packages,
    admin_smes,
    admin_sponsor,
    admin_waiting_list,
    assessment,
    auth,
    courses,
    health,
    landing,
    media,
    my,
    player,
    policies,
    register,
    review,
    site,
    sponsor,
)
from app.services.ffprobe import ensure_ffprobe_available
from app.storage import ensure_bucket_versioning, get_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at boot, with every violation listed, not one restart at a
    # time in production — and not at first upload if ffprobe is missing.
    ensure_boot_config(settings)
    if settings.env == "prod":
        ensure_bucket_versioning(get_storage())
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
app.include_router(admin_waiting_list.router, prefix="/api/v1")
app.include_router(assessment.router, prefix="/api/v1")
app.include_router(assessment.admin_router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(landing.router, prefix="/api/v1")
# Under Spaces, video plays from presigned URLs and /media/ must 404;
# the route simply does not exist.
if settings.storage_backend == "local":
    app.include_router(media.router, prefix="/api/v1")
app.include_router(my.router, prefix="/api/v1")
app.include_router(player.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(policies.admin_router, prefix="/api/v1")
app.include_router(register.router, prefix="/api/v1")
app.include_router(register.admin_router, prefix="/api/v1")
app.include_router(sponsor.router, prefix="/api/v1")
