# The API image. Build context is the repo root (see docker-compose.yml).
FROM python:3.12-slim

# ffprobe is a boot requirement (002): every uploaded video's duration is
# measured with it (7.02.7).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin supercpe

WORKDIR /srv/app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# The git sha deploy.sh passes in; /api/v1/health reports it, which is
# how the deploy verifies the new code is actually the one running.
ARG GIT_SHA=dev
ENV APP_VERSION=${GIT_SHA}

USER supercpe
EXPOSE 8000

# Migrations are NOT run here: deploy.sh runs `alembic upgrade head` as
# its own one-off container before starting this command, so a failed
# migration stops the deploy instead of crash-looping the API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
