# Dockerfile — detecktiv-io API (FastAPI + Alembic + Gunicorn/Uvicorn)
# Safe, production-lean build that still supports local dev. Additive (doesn't remove features).

FROM python:3.12-slim-bookworm

# --- Environment hygiene ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Prometheus multiprocess metrics directory
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus \
    # Default API port/workers (can be overridden by env/compose)
    API_PORT=8000 \
    PORT=8000 \
    API_WORKERS=1 \
    # Alembic config path (env.py will build the DB URL from env)
    ALEMBIC_CONFIG=/app/alembic.ini \
    # Optional: keep stdout/stderr structured; tweak without changing CMD
    GUNICORN_CMD_ARGS="--graceful-timeout 30 --keep-alive 5" \
    # Ensure modules import cleanly
    PYTHONPATH=/app

# --- System deps (runtime only; keep slim) ---
# - curl for HEALTHCHECK
# - libpq for psycopg/psycopg2-binary at runtime on some platforms
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

# --- Create app user & dirs ---
RUN useradd -m -u 10001 app \
 && mkdir -p /app /tmp/prometheus \
 && chown -R app:app /app /tmp/prometheus

WORKDIR /app

# --- Install Python deps first (leverages Docker layer cache) ---
# Copy requirements from new structure
COPY backend/requirements/base.txt /app/requirements/base.txt
COPY backend/requirements/prod.txt /app/requirements/prod.txt
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install -r /app/requirements/prod.txt

# --- Copy backend project files ---
# NOTE: .env is typically provided by docker-compose and NOT baked into the image.
COPY backend/ /app/
RUN chown -R app:app /app

USER app

# --- Expose API port (informational) ---
EXPOSE 8000

# --- Healthcheck (simple liveness via /health) ---
HEALTHCHECK --interval=30s --timeout=4s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-${API_PORT:-8000}}/health" || exit 1

# --- Default command ---
# - Run Alembic migrations if enabled (RUN_MIGRATIONS_ON_BOOT=1)
# - Start Gunicorn with Uvicorn workers
#
# Env used (override in compose if needed):
#   RUN_MIGRATIONS_ON_BOOT=1|0
#   MIGRATION_TARGET=head (or a specific revision)
#   POSTGRES_* / DATABASE_URL / DB_SCHEMA (picked up by alembic/env.py)
#
CMD ["/bin/sh", "-lc", "\
  if [ \"${RUN_MIGRATIONS_ON_BOOT:-1}\" = \"1\" ]; then \
    echo '[entrypoint] Running Alembic migrations to ${MIGRATION_TARGET:-head}'; \
    alembic upgrade ${MIGRATION_TARGET:-head}; \
  else \
    echo '[entrypoint] Skipping Alembic migrations (RUN_MIGRATIONS_ON_BOOT!=1)'; \
  fi; \
  echo '[entrypoint] Starting Gunicorn on 0.0.0.0:'${PORT:-${API_PORT:-8000}}; \
  exec gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-${API_PORT:-8000}} \
    --workers ${API_WORKERS:-1} \
    --timeout 90 \
    --access-logfile - \
    --error-logfile - \
"]

# ---------------------------------------------------------------------------
# Notes
# - Alembic uses alembic/env.py, which reads DATABASE_URL or POSTGRES_* from env.
# - Metrics: PROMETHEUS_MULTIPROC_DIR is created and writable for multiprocess mode.
# - Security: runs as non-root 'app' user (uid 10001).
# - If you need autoreload in dev, override command in docker-compose with:
#     command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# - This image is API-only; frontend assets are served by the dedicated frontend container.
# ---------------------------------------------------------------------------
