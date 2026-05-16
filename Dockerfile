# Single image with two entrypoints:
#   web  -> uvicorn / FastAPI (Cloud Run Service)
#   sync -> hcw-sync CLI       (Cloud Run Job invoked by Cloud Scheduler)
# Switch with the container's CMD or `args` field.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OS deps. libpq for psycopg (binary wheel doesn't always ship for slim).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Source-of-truth TOML files for the supplement stack and herbal teas. The sync
# job reads both on each run and upserts into the DB. Kept outside the package
# so non-Python tooling (linters, GitLab UI) can read them directly from the repo.
COPY vitamins.toml teas.toml ./

# Drop privileges
RUN useradd -u 1000 -m hcw && chown -R hcw:hcw /app
USER hcw

# Cloud Run sets $PORT; uvicorn picks it up via the entrypoint module.
ENV PORT=8080 HOST=0.0.0.0 APP_ENV=prod

# Default entrypoint = web app. Override CMD to "hcw-sync" for the sync job.
CMD ["hcw-web"]
