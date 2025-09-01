# Base image
FROM python:3.13-slim

# Environment
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# System deps:
# - bash: entrypoint uses bash features
# - curl, postgresql-client: used by entrypoint/health checks
# - build-essential, libpq-dev: safe for psycopg2/psycopg builds
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash \
      curl \
      postgresql-client \
      build-essential \
      libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Unprivileged user
RUN useradd -ms /bin/bash appuser

WORKDIR /app

# Install Python deps with cache-friendly layering
# (If you only have requirements.txt, the wildcard still works.)
COPY requirements*.txt ./
RUN python -m pip install --upgrade pip \
 && if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Copy the rest of the app
COPY . /app

# Always use the repo's docker/entrypoint.sh as the runtime entrypoint
# - Force copy (overwrites any existing /app/entrypoint.sh)
# - Strip CRLF (Windows) to LF
# - Make executable
RUN cp -f /app/docker/entrypoint.sh /app/entrypoint.sh \
 && sed -i 's/\r$//' /app/entrypoint.sh \
 && chmod +x /app/entrypoint.sh \
 && chown -R appuser:appuser /app

# Let Alembic tools/scripts work out of the box (can be overridden)
ENV ALEMBIC_CONFIG=/app/alembic.ini

# Expose API port
EXPOSE 8000

# Run as non-root
USER appuser

# Normal startup: entrypoint does DB wait/migrations gating, then execs uvicorn
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
