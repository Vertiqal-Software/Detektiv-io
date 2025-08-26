#!/bin/sh
set -eu

echo "== Entrypoint starting =="

# Normalize env (defaults for dev)
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-detecktiv}"
ALEMBIC_CONFIG="${ALEMBIC_CONFIG:-/app/alembic.ini}"

export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT POSTGRES_DB ALEMBIC_CONFIG

echo "ALEMBIC_CONFIG=$ALEMBIC_CONFIG"
cd /app 2>/dev/null || true
if [ ! -f "$ALEMBIC_CONFIG" ]; then
  echo "FATAL: alembic.ini not found at $ALEMBIC_CONFIG"
  ls -la /app || true
  exit 1
fi
echo "alembic.ini is present."

# Masked DSN for logs
echo "DB URL (masked): postgresql+psycopg2://${POSTGRES_USER}:***@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}?sslmode=disable"

echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
i=0
while [ $i -lt 60 ]; do
  i=$((i+1))
  if PGPASSWORD="${POSTGRES_PASSWORD}" \
     psql "host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB} user=${POSTGRES_USER} sslmode=disable" \
     -c "select 1" >/dev/null 2>&1; then
    echo "Postgres is ready."
    break
  fi
  sleep 1
done
if [ $i -ge 60 ]; then
  echo "FATAL: Postgres never became ready."
  exit 1
fi

echo "Running Alembic migrations."
python -m alembic upgrade head

echo "== Entrypoint migration phase complete, starting API =="
exec "$@"