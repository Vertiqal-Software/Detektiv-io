# alembic/env.py
# Updated add-only: kept your logic intact and added safe enhancements:
# - Optional DB wait loop (WAIT_FOR_DB_MAX_TRIES / WAIT_FOR_DB_SLEEP_SECS) for containerized boots
# - include_object filter to avoid migrating objects outside target schema and to skip version table
# - process_revision_directives to auto-skip empty autogenerate revisions
# - Small logging improvements
# - NEW: Revision-chain integrity check (logs missing down_revision targets; optional strict mode)

from __future__ import annotations

import os
import sys
import time
import logging
from logging.config import fileConfig
from typing import Iterable, List, Optional, Tuple

from alembic import context
from sqlalchemy import create_engine, pool, text

# --------------------------------------------------------------------------
# Alembic Config + Logging
# --------------------------------------------------------------------------
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Ensure the project root is importable when running from /alembic
sys.path.append(os.getcwd())


# --------------------------------------------------------------------------
# URL & schema helpers
# --------------------------------------------------------------------------
def _normalize_driver(url: str) -> str:
    """Ensure Postgres DSN has an explicit driver."""
    try:
        if "+psycopg" in url or "+psycopg2" in url or "+asyncpg" in url:
            return url
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://") :]
        return url
    except Exception:
        return url


def _bool_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on", "y"}


def _build_postgres_dsn() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "detecktiv")
    sslmode = (os.getenv("POSTGRES_SSLMODE") or "").strip()
    q = f"?sslmode={sslmode}" if sslmode else ""
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}{q}"


def _build_db_url() -> str:
    """
    Build the database URL from env, preferring DATABASE_URL.
    Falls back to POSTGRES_* vars used by docker-compose.

    Safety override: if DATABASE_URL refers to SQLite but POSTGRES_* is present
    (typical in Docker) or FORCE_POSTGRES=1, prefer the Postgres DSN to avoid
    running PG-specific migrations on SQLite.
    """
    raw = (os.getenv("DATABASE_URL") or "").strip()
    has_pg_vars = any(os.getenv(k) for k in ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_DB"))
    force_pg = _bool_env("FORCE_POSTGRES", False)

    if raw:
        if raw.startswith("sqlite") and (has_pg_vars or force_pg):
            return _build_postgres_dsn()
        return _normalize_driver(raw)

    # No DATABASE_URL provided → build from POSTGRES_* (Docker default)
    return _build_postgres_dsn()


def _schema() -> str:
    return (
        (os.getenv("ALEMBIC_SCHEMA") or "").strip()
        or (os.getenv("POSTGRES_SCHEMA") or "").strip()
        or (os.getenv("DB_SCHEMA") or "").strip()
        or "public"
    )


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite://")


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


# Compute URL + schema and push URL into Alembic config
URL = _build_db_url()
SCHEMA = _schema()
config.set_main_option("sqlalchemy.url", URL)

# --------------------------------------------------------------------------
# Target metadata from your app (keeps ORM & Alembic aligned)
# --------------------------------------------------------------------------
def _import_target_metadata():
    """
    Prefer app.models.base.get_metadata(); fall back to Base.metadata.
    As a last resort, try app.models:Base (older layouts).
    """
    try:
        from app.models.base import get_metadata  # type: ignore
        return get_metadata()
    except Exception:
        try:
            from app.models.base import Base  # type: ignore
            return Base.metadata  # type: ignore[attr-defined]
        except Exception:
            try:
                from app.models import Base  # type: ignore
                return Base.metadata  # type: ignore[attr-defined]
            except Exception:
                return None


target_metadata = _import_target_metadata()

# Autogenerate tuning
compare_type = True
compare_server_default = True

# Schemas / version table placement
include_schemas = _is_postgres(URL)
version_table = config.get_main_option("version_table", "alembic_version")
version_table_schema = SCHEMA if _is_postgres(URL) else None

# SQLite DDL safety
render_as_batch = _is_sqlite(URL)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _ensure_version_table(connection) -> None:
    """
    Ensure the alembic version table exists with a sufficiently large column.
    Default Alembic uses VARCHAR(32); we use 255 to support long revision ids.
    Also try to widen the column if it already exists with a smaller size.
    """
    if _is_postgres(URL):
        # Ensure schema exists
        try:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        except Exception:
            pass
        # Create table if missing (with VARCHAR(255))
        try:
            connection.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS "{SCHEMA}"."{version_table}" ('
                    "version_num VARCHAR(255) NOT NULL, "
                    f"CONSTRAINT {version_table}_pk PRIMARY KEY (version_num)"
                    ")"
                )
            )
        except Exception:
            pass
        # Try to widen existing column (no-op if already wide)
        try:
            connection.execute(
                text(
                    f'ALTER TABLE "{SCHEMA}"."{version_table}" '
                    "ALTER COLUMN version_num TYPE VARCHAR(255)"
                )
            )
        except Exception:
            # Ignore if ALTER not needed or lacking perms
            pass
    elif _is_sqlite(URL):
        # SQLite: best-effort create if missing (no easy ALTER TYPE)
        try:
            connection.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS "{version_table}" ('
                    "version_num VARCHAR(255) NOT NULL PRIMARY KEY"
                    ")"
                )
            )
        except Exception:
            pass


# --- Added: filter objects to migrate (keep to our target schema; skip version table) ---
def _include_object(object_, name, type_, reflected, compare_to):
    # Skip Alembic's own version table
    if type_ == "table" and name == version_table:
        return False

    # For Postgres, restrict to our configured schema (allow public for extensions if needed)
    if _is_postgres(URL):
        obj_schema = getattr(object_, "schema", None)
        if type_ in {"table", "column", "index", "unique_constraint", "foreign_key_constraint", "check_constraint"}:
            # Many objects hang off a table; try to read its table's schema
            table = getattr(object_, "table", None)
            table_schema = getattr(table, "schema", None)
            effective_schema = obj_schema or table_schema
            if effective_schema and str(effective_schema) != SCHEMA:
                return False

    return True


# --- Added: autogenerate helper to skip empty revisions gracefully ---
def _process_revision_directives(context_, revision, directives):
    try:
        cmd_opts = config.cmd_opts  # type: ignore[attr-defined]
    except Exception:
        cmd_opts = None

    if cmd_opts and getattr(cmd_opts, "autogenerate", False):
        if directives:
            script = directives[0]
            if hasattr(script, "upgrade_ops") and script.upgrade_ops.is_empty():
                logger.info("No schema changes detected; skipping empty migration file.")
                directives[:] = []


# --- NEW: revision chain integrity check ------------------------------------
def _log_revision_locations():
    try:
        # These options may or may not be set in alembic.ini
        vps = config.get_main_option("version_path_separator", default=None)
        vlocs = config.get_main_option("version_locations", default=None)
        sloc = config.get_main_option("script_location", default=None)
        logger.info(
            "Alembic paths — script_location=%r, version_path_separator=%r, version_locations=%r",
            sloc, vps, vlocs
        )
    except Exception:
        pass


def _check_revision_chain() -> None:
    """
    Inspect the migrations directory (or directories) and report:
      - Missing down_revision targets
      - Multiple heads (warning by default; strict if ALEMBIC_STRICT_CHAIN=1)

    Behavior:
      - Controlled by ALEMBIC_CHECK_CHAIN (default: true)
      - If ALEMBIC_STRICT_CHAIN=1 and issues exist, raise RuntimeError to halt
    """
    from alembic.script import ScriptDirectory  # local import; alembic provides it

    if not _bool_env("ALEMBIC_CHECK_CHAIN", True):
        logger.info("ALEMBIC_CHECK_CHAIN=0 — skipping revision chain check.")
        return

    try:
        script = ScriptDirectory.from_config(config)
    except Exception as e:
        logger.warning("Could not initialize ScriptDirectory to check chain: %s", e)
        return

    # Collect all revisions
    try:
        all_revs = list(script.walk_revisions())
    except Exception as e:
        logger.warning("Failed to walk revisions: %s", e)
        return

    # Map revisions by id for quick lookup
    by_id = {rev.revision: rev for rev in all_revs}

    # Detect missing down_revision links
    missing: List[Tuple[str, Optional[str], Optional[str]]] = []
    for rev in all_revs:
        downs: Iterable[Optional[str]]
        if isinstance(rev.down_revision, tuple):
            downs = rev.down_revision
        else:
            downs = (rev.down_revision,)  # type: ignore[assignment]
        for d in downs:
            if d is None:
                continue
            if d not in by_id:
                missing.append((rev.revision, d, rev.path if hasattr(rev, "path") else None))

    # Detect multiple heads
    try:
        heads = list(script.get_heads())
    except Exception:
        heads = []

    if missing:
        logger.error("Alembic revision chain has %d missing down_revision target(s):", len(missing))
        for (rev_id, missing_id, path) in missing:
            logger.error("  - Revision %s references missing down_revision %s (file: %s)", rev_id, missing_id, path)

    if len(heads) > 1:
        logger.warning(
            "Alembic currently has %d heads: %s. Consider merging heads or enabling multi-dir version_locations.",
            len(heads), ", ".join(heads),
        )

    if (missing or len(heads) > 1) and _bool_env("ALEMBIC_STRICT_CHAIN", False):
        raise RuntimeError(
            "Revision chain integrity check failed. Set ALEMBIC_STRICT_CHAIN=0 to allow, "
            "or fix missing down_revision targets / multiple heads."
        )


# --------------------------------------------------------------------------
# Migration runners
# --------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (no DB connection).
    """
    # Log locations and sanity-check chain before configure
    _log_revision_locations()
    _check_revision_chain()

    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=compare_type,
        compare_server_default=compare_server_default,
        include_schemas=include_schemas,
        # Version table lives in our chosen schema for Postgres
        version_table=version_table,
        version_table_schema=version_table_schema,
        dialect_opts={"paramstyle": "named"},
        # default_schema is a hint for autogenerate; schema-qualifying still occurs via include_schemas
        default_schema=SCHEMA if _is_postgres(URL) else None,
        render_as_batch=render_as_batch,
        include_object=_include_object,                 # <-- added
        process_revision_directives=_process_revision_directives,  # <-- added
    )

    with context.begin_transaction():
        context.run_migrations()


def _connect_with_retries(engine):
    """
    Added: optional wait-for-DB loop controlled by:
      WAIT_FOR_DB_MAX_TRIES (default 1 = no wait)
      WAIT_FOR_DB_SLEEP_SECS (default 1)
    """
    max_tries = int(os.getenv("WAIT_FOR_DB_MAX_TRIES", "1") or "1")
    sleep_secs = float(os.getenv("WAIT_FOR_DB_SLEEP_SECS", "1") or "1")

    last_err = None
    for attempt in range(1, max_tries + 1):
        try:
            conn = engine.connect()
            if attempt > 1:
                logger.info("Connected to DB after %d attempt(s).", attempt)
            return conn
        except Exception as e:  # pragma: no cover
            last_err = e
            if attempt >= max_tries:
                break
            logger.warning(
                "DB not ready (attempt %d/%d): %s; retrying in %ss",
                attempt, max_tries, getattr(e, "args", e), sleep_secs,
            )
            time.sleep(sleep_secs)
    # Exhausted retries
    raise last_err  # type: ignore[misc]


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (with DB connection).
    """
    # Log locations and sanity-check chain early
    _log_revision_locations()
    _check_revision_chain()

    connectable = create_engine(URL, poolclass=pool.NullPool, future=True)

    # Added: optional retries when DB isn't ready yet (e.g., containers)
    connection = _connect_with_retries(connectable)

    with connection:
        # For Postgres, ensure schema exists and set search_path for this session
        if _is_postgres(URL):
            try:
                connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
            except Exception:
                # Non-fatal; proceed even if schema cannot be created (permissions, etc.)
                pass
            try:
                # Include public as fallback for extensions/functions
                connection.execute(text(f"SET search_path TO {SCHEMA}, public"))
            except Exception:
                pass

        # Ensure/widen version table BEFORE Alembic writes to it
        _ensure_version_table(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=compare_type,
            compare_server_default=compare_server_default,
            include_schemas=include_schemas,
            version_table=version_table,
            version_table_schema=version_table_schema,
            default_schema=SCHEMA if _is_postgres(URL) else None,
            render_as_batch=render_as_batch,
            include_object=_include_object,                 # <-- added
            process_revision_directives=_process_revision_directives,  # <-- added
        )

        with context.begin_transaction():
            context.run_migrations()


# Entrypoint
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
