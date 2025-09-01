#!/usr/bin/env bash
set -euo pipefail

echo "== Entrypoint starting =="

# -------------------------
# Base env (defaults)
# -------------------------
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-detecktiv}"
POSTGRES_SSLMODE="${POSTGRES_SSLMODE:-disable}"

ALEMBIC_CONFIG="${ALEMBIC_CONFIG:-/app/alembic.ini}"
RUN_MIGRATIONS_ON_BOOT="${RUN_MIGRATIONS_ON_BOOT:-1}"

# Optional: DB wait tuning
WAIT_FOR_DB_MAX_TRIES="${WAIT_FOR_DB_MAX_TRIES:-60}"
WAIT_FOR_DB_SLEEP_SECS="${WAIT_FOR_DB_SLEEP_SECS:-1}"

# If set to 1, skip waiting for DB (useful for non-PG URLs)
ENTRYPOINT_SKIP_DB_WAIT="${ENTRYPOINT_SKIP_DB_WAIT:-0}"

# New (non-breaking): migration target & options
MIGRATION_TARGET="${MIGRATION_TARGET:-head}"              # e.g., "head" or a specific revision
ALEMBIC_EXTRA_OPTS="${ALEMBIC_EXTRA_OPTS:-}"              # e.g., "-c /app/alembic.ini -x data=true"
PREMIGRATION_SQL="${PREMIGRATION_SQL:-}"                  # e.g., "/app/scripts/init.sql"
APP_WAIT_FOR_DB_SQL="${APP_WAIT_FOR_DB_SQL:-select 1}"    # customizable readiness query

export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_SSLMODE \
  ALEMBIC_CONFIG RUN_MIGRATIONS_ON_BOOT WAIT_FOR_DB_MAX_TRIES WAIT_FOR_DB_SLEEP_SECS ENTRYPOINT_SKIP_DB_WAIT \
  MIGRATION_TARGET ALEMBIC_EXTRA_OPTS PREMIGRATION_SQL APP_WAIT_FOR_DB_SQL

# Normalize booleans for RUN_MIGRATIONS_ON_BOOT (non-breaking enhancement)
case "${RUN_MIGRATIONS_ON_BOOT,,}" in
  1|true|yes|y) RUN_MIGRATIONS_ON_BOOT="1" ;;
  0|false|no|n) RUN_MIGRATIONS_ON_BOOT="0" ;;
esac
export RUN_MIGRATIONS_ON_BOOT

# Ensure app is importable
export PYTHONPATH="/app:${PYTHONPATH:-}"

echo "ALEMBIC_CONFIG=$ALEMBIC_CONFIG"
cd /app 2>/dev/null || true
if [ ! -f "$ALEMBIC_CONFIG" ]; then
  echo "FATAL: alembic.ini not found at $ALEMBIC_CONFIG"
  ls -la /app || true
  exit 1
fi
echo "alembic.ini is present."

# -------------------------------------------
# Prefer DATABASE_URL if provided:
# - Parse into POSTGRES_* for readiness checks
# - Create a masked printable variant
# - Auto-skip DB wait if not 'postgres*' scheme
# -------------------------------------------
eval "$(python - <<'PY'
import os, sys, urllib.parse

def shq(s: str) -> str:
    # shell-quote with single quotes
    return "'" + s.replace("'", "'\"'\"'") + "'"

url = os.getenv("DATABASE_URL", "")
if not url:
    # Nothing to export; rely on POSTGRES_* already set
    sys.exit(0)

p = urllib.parse.urlparse(url)
scheme = (p.scheme or "").lower()

# If not a Postgres scheme, skip DB wait (e.g., sqlite)
if not scheme.startswith("postgres"):
    print("export ENTRYPOINT_SKIP_DB_WAIT='1'")
    # Masking best-effort
    masked = url
    if p.password:
        masked = url.replace(p.password, "***")
    else:
        # Try to mask cred section conservatively
        ssep = url.find("://")
        if ssep != -1 and "@" in url[ssep+3:]:
            cred_end = url.find("@", ssep+3)
            cred = url[ssep+3:cred_end]
            if ":" in cred:
                user_part = cred.split(":", 1)[0]
                masked = url[:ssep+3] + f"{user_part}:***" + url[ssep+3+len(cred):]
    print(f"export ENTRYPOINT_MASKED_DB_URL={shq(masked)}")
    sys.exit(0)

# For Postgres URLs, normalize into POSTGRES_* for readiness checks
user = urllib.parse.unquote(p.username or os.getenv("POSTGRES_USER","postgres"))
password = urllib.parse.unquote(p.password or os.getenv("POSTGRES_PASSWORD",""))
host = p.hostname or os.getenv("POSTGRES_HOST","postgres")
port = str(p.port or os.getenv("POSTGRES_PORT","5432"))
db = (p.path or "/").lstrip("/") or os.getenv("POSTGRES_DB","detecktiv")
q = urllib.parse.parse_qs(p.query)
sslmode = (q.get("sslmode", [os.getenv("POSTGRES_SSLMODE","disable")])[0]) or "disable"

# Masked URL for logs
masked = url
if p.password:
    masked = url.replace(p.password, "***")
else:
    ssep = url.find("://")
    if ssep != -1 and "@" in url[ssep+3:]:
        cred_end = url.find("@", ssep+3)
        cred = url[ssep+3:cred_end]
        if ":" in cred:
            user_part = cred.split(":", 1)[0]
            masked = url[:ssep+3] + f"{user_part}:***" + url[ssep+3+len(cred):]

print(f"export POSTGRES_USER={shq(user)}")
print(f"export POSTGRES_PASSWORD={shq(password)}")
print(f"export POSTGRES_HOST={shq(host)}")
print(f"export POSTGRES_PORT={shq(port)}")
print(f"export POSTGRES_DB={shq(db)}")
print(f"export POSTGRES_SSLMODE={shq(sslmode)}")
print(f"export ENTRYPOINT_MASKED_DB_URL={shq(masked)}")
PY
)"

# Masked DSN line (fallback if Python block didn't set it)
if [ -z "${ENTRYPOINT_MASKED_DB_URL:-}" ]; then
  ENTRYPOINT_MASKED_DB_URL="postgresql+psycopg2://${POSTGRES_USER}:***@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}?sslmode=${POSTGRES_SSLMODE}"
fi
echo "DB URL (masked): ${ENTRYPOINT_MASKED_DB_URL}"

# -------------------------
# Wait for Postgres (optional)
# -------------------------
if [ "${ENTRYPOINT_SKIP_DB_WAIT}" = "1" ]; then
  echo "Skipping DB wait (ENTRYPOINT_SKIP_DB_WAIT=1)."
else
  echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT} (sslmode=${POSTGRES_SSLMODE})..."
  i=0
  if command -v psql >/dev/null 2>&1; then
    until [ $i -ge "${WAIT_FOR_DB_MAX_TRIES}" ]; do
      i=$((i+1))
      if PGPASSWORD="$POSTGRES_PASSWORD" \
         psql "host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB} user=${POSTGRES_USER} sslmode=${POSTGRES_SSLMODE}" \
         -c "${APP_WAIT_FOR_DB_SQL}" >/dev/null 2>&1; then
        echo "Postgres is ready."
        break
      fi
      sleep "${WAIT_FOR_DB_SLEEP_SECS}"
    done
  else
    echo "psql not found; using Python/SQLAlchemy fallback for DB readiness."
    python - <<PY || true
import os, time, sys
from sqlalchemy import create_engine, text
url = os.getenv("DATABASE_URL")
if not url:
    # Build from POSTGRES_* if DATABASE_URL not set
    user = os.getenv("POSTGRES_USER","postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD","")
    host = os.getenv("POSTGRES_HOST","postgres")
    port = os.getenv("POSTGRES_PORT","5432")
    db   = os.getenv("POSTGRES_DB","detecktiv")
    ssl  = os.getenv("POSTGRES_SSLMODE","disable")
    url  = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}?sslmode={ssl}"
tries = int(os.getenv("WAIT_FOR_DB_MAX_TRIES","60"))
delay = float(os.getenv("WAIT_FOR_DB_SLEEP_SECS","1"))
sql   = os.getenv("APP_WAIT_FOR_DB_SQL","select 1")
last = None
for i in range(1, tries+1):
    try:
        eng = create_engine(url, future=True)
        with eng.connect() as conn:
            conn.execute(text(sql)).scalar_one()
        print("Postgres is ready (Python fallback).")
        sys.exit(0)
    except Exception as e:
        last = e
        time.sleep(delay)
print("FATAL: Postgres never became ready (Python fallback).", last)
sys.exit(1)
PY
  fi
  if [ $i -ge "${WAIT_FOR_DB_MAX_TRIES}" ]; then
    echo "FATAL: Postgres never became ready after ${WAIT_FOR_DB_MAX_TRIES} attempts."
    exit 1
  fi
fi

# ---------------------------------
# Optional pre-migration SQL file
# ---------------------------------
if [ -n "${PREMIGRATION_SQL}" ] && [ -f "${PREMIGRATION_SQL}" ]; then
  echo "Running pre-migration SQL: ${PREMIGRATION_SQL}"
  if command -v psql >/dev/null 2>&1; then
    PGPASSWORD="$POSTGRES_PASSWORD" \
    psql "host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB} user=${POSTGRES_USER} sslmode=${POSTGRES_SSLMODE}" \
      -f "${PREMIGRATION_SQL}" || true
  else
    echo "psql not available; skipping PREMIGRATION_SQL execution."
  fi
fi

# ---------------------------------
# Optional guard to skip migrations
# ---------------------------------
if [ "${RUN_MIGRATIONS_ON_BOOT}" != "1" ]; then
  echo "[entrypoint] RUN_MIGRATIONS_ON_BOOT=${RUN_MIGRATIONS_ON_BOOT} -> will skip applying migrations."
  python() {
    if [ "${1:-}" = "-m" ] && [ "${2:-}" = "alembic" ] && [ "${3:-}" = "upgrade" ] && [ "${4:-}" = "head" ]; then
      echo "[entrypoint] Skipping DB migrations (alembic upgrade head)"
      return 0
    fi
    command python "$@"
  }
fi

# Quick check: ensure alembic is importable (fixed here-doc syntax)
if ! python - >/dev/null 2>&1 <<'PY'
import importlib, sys
sys.exit(0 if importlib.util.find_spec("alembic") else 1)
PY
then
  echo "FATAL: Alembic is not installed in the environment. Did you install requirements?"
  exit 1
fi

echo "Running Alembic migrations."
# Preserve your original invocation style (python -m), with new options supported.
if [ -n "${ALEMBIC_EXTRA_OPTS}" ]; then
  # shellcheck disable=SC2086
  python -m alembic ${ALEMBIC_EXTRA_OPTS} upgrade "${MIGRATION_TARGET}"
else
  python -m alembic upgrade "${MIGRATION_TARGET}"
fi

echo "== Entrypoint migration phase complete, starting API =="
echo "exec: $*"
exec "$@"
