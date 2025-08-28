# Dockerfile
FROM python:3.13-slim

# Prevent interactive tzdata etc.
ENV DEBIAN_FRONTEND=noninteractive

# Install minimal tools needed by entrypoint and healthcheck:
# - postgresql-client: provides `psql` used by entrypoint.sh
# - curl: used by the container healthcheck command
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*

# Create an unprivileged user (optional but recommended)
RUN useradd -ms /bin/bash appuser

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY requirements.txt ./requirements.txt
# If you have dev extras, don't install them here:
# COPY requirements-dev.txt ./requirements-dev.txt

# Install python deps (pin versions in requirements.txt)
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source
COPY . .

# Ensure entrypoint is executable
RUN chmod +x docker/entrypoint.sh

# Run as non-root
USER appuser

# Alembic config expected at /app/alembic.ini per compose env
# Entrypoint will run migrations then exec the CMD below
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Start the API (FastAPI via uvicorn)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
