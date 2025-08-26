FROM python:3.13-slim

# psql is required by docker/entrypoint.sh; curl used by compose healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install runtime deps
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Bring in app + migrations + entrypoint
COPY alembic.ini ./ 
COPY db ./db
COPY app ./app
COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod +x ./docker/entrypoint.sh

# Helpful envs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALEMBIC_CONFIG=/app/alembic.ini

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]

EXPOSE 8000
