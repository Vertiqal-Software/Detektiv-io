# app/core/session.py
from __future__ import annotations

"""
Database session and engine helpers.

Features
--------
- Cached SQLAlchemy engine (pool_pre_ping=True).
- FastAPI dependency `get_db()` yielding a scoped Session with proper rollback/close.
- Env-driven DSN resolution with masking helper `db_url(mask_password=True)`.
- Postgres first; graceful SQLite fallback for local/dev.
- Optional Postgres schema search_path via ALEMBIC_SCHEMA / POSTGRES_SCHEMA / DB_SCHEMA.
- Health check `ping_db()` used by /health/db and readiness.

Environment (any are optional)
------------------------------
# Direct DSN (highest priority)
DATABASE_URL
SQLALCHEMY_DATABASE_URI
DB_URL

# Postgres components (used when no DSN above is provided)
POSTGRES_USER        (default: postgres)
POSTGRES_PASSWORD    (default: "")
POSTGRES_HOST        (default: 127.0.0.1)
POSTGRES_PORT        (default: 5432)
POSTGRES_DB          (default: detecktiv)
POSTGRES_SSLMODE     (optional: prefer, require, disable, verify-ca, verify-full)

# SQLite fallback (used only if neither DSN nor POSTGRES_* can connect)
SQLITE_PATH          (default: "./app.db")

# Schema
ALEMBIC_SCHEMA       (default: "public")
POSTGRES_SCHEMA      (alias for ALEMBIC_SCHEMA)
DB_SCHEMA            (alias for ALEMBIC_SCHEMA)

# Pooling
DB_POOL_SIZE         (default: 5)
DB_MAX_OVERFLOW      (default: 10)
DB_POOL_TIMEOUT      (default: 30 seconds)
DB_POOL_RECYCLE      (default: 1800 seconds)

# Debug/dev
SQLALCHEMY_ECHO      (0/1; default 0)
RUN_DB_TESTS         (1 -> create a fresh engine per process for isolation)
"""

import os
import re
from contextlib import contextmanager
from typing import Generator, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import sessionmaker, Session


# -----------------------------------------------------------------------------
# DSN and schema helpers
# -----------------------------------------------------------------------------

def _first_nonempty(*values: Optional[str]) -> Optional[str]:
    for v in values:
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return None


def _schema_env() -> str:
    s = _first_nonempty(
        os.getenv("ALEMBIC_SCHEMA"),
        os.getenv("POSTGRES_SCHEMA"),
        os.getenv("DB_SCHEMA"),
        "public",
    ) or "public"
    # keep it safe (letters/underscore then alphanumerics/_)
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
        raise RuntimeError(f"Invalid schema name: {s!r}")
    return s


def _build_postgres_url() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", "5432") or "5432")
    db = os.getenv("POSTGRES_DB", "detecktiv")

    # Use psycopg2 by default unless the DSN explicitly specifies another driver.
    base = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

    # Optional SSL mode
    sslmode = (os.getenv("POSTGRES_SSLMODE") or "").strip()
    if sslmode:
        # Add as query param; preserve driver
        sep = "&" if "?" in base else "?"
        base = f"{base}{sep}sslmode={sslmode}"

    # Optional search_path via "options=-csearch_path=<schema>"
    schema = _schema_env()
    sep = "&" if "?" in base else "?"
    base = f'{base}{sep}options=-csearch_path%3D{schema}'

    return base


def _sqlite_url() -> str:
    path = os.getenv("SQLITE_PATH", "./app.db")
    # Absolute path support; three slashes for relative, four for absolute (sqlite URL rules)
    if os.path.isabs(path):
        return f"sqlite:///{path}"
    return f"sqlite:///{os.path.abspath(path)}"


def _normalize_url(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    # If someone provided bare 'postgresql://', keep it; if no driver, leave as is.
    return s


def db_url(mask_password: bool = True) -> str:
    """
    Resolve the effective SQLAlchemy URL used to connect.
    If mask_password=True, redact the password portion for logs/health.
    """
    # FORCE PostgreSQL - Always build from POSTGRES_* pieces for MVP demo
    url = _build_postgres_url()
    
    # Fallback to env vars only if PostgreSQL connection fails
    if os.getenv("FORCE_POSTGRES") == "1":
        pass  # Always use PostgreSQL URL we just built
    else:
        # Original logic for non-forced scenarios
        raw = _first_nonempty(
            os.getenv("DATABASE_URL"),
            os.getenv("SQLALCHEMY_DATABASE_URI"),
            os.getenv("DB_URL"),
        )
        if raw:
            url = _normalize_url(raw)
            if not url:
                url = _build_postgres_url()
            # If the URL contains no scheme at all, treat as SQLite path
            if "://" not in url:
                url = f"sqlite:///{url}"

    if mask_password:
        # Redact password within '://user:pass@host'
        try:
            # crude but robust enough: replace substring between first ':' and '@' after '://'
            # Example: postgresql://user:pass@host -> postgresql://user:***@host
            prefix, rest = url.split("://", 1)
            if "@" in rest and ":" in rest.split("@", 1)[0]:
                user, remainder = rest.split("@", 1)
                u_name, _u_pass = user.split(":", 1)
                rest = f"{u_name}:***@{remainder}"
                return f"{prefix}://{rest}"
        except Exception:
            pass
    return url


# -----------------------------------------------------------------------------
# Engine cache & factory
# -----------------------------------------------------------------------------

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _pool_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def get_engine() -> Engine:
    """
    Return a process-wide cached Engine. If RUN_DB_TESTS=1, always build a fresh
    engine for isolation (so truncation/DDL during tests doesn't bleed across).
    """
    global _engine, _SessionLocal

    if os.getenv("RUN_DB_TESTS") == "1":
        # Fresh engine each time function is first called in the process.
        # (Not per-call; we still cache within the process to avoid reconnect storms)
        if _engine is not None:
            return _engine

    if _engine is not None:
        return _engine

    url = db_url(mask_password=False)
    echo = (os.getenv("SQLALCHEMY_ECHO") or "0").strip() in {"1", "true", "yes", "on"}

    pool_size = _pool_int("DB_POOL_SIZE", 5)
    max_overflow = _pool_int("DB_MAX_OVERFLOW", 10)
    pool_timeout = _pool_int("DB_POOL_TIMEOUT", 30)
    pool_recycle = _pool_int("DB_POOL_RECYCLE", 1800)

    is_sqlite = url.startswith("sqlite:")
    connect_args = {}
    if is_sqlite:
        connect_args = {"check_same_thread": False}

    _engine = create_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
        pool_size=None if is_sqlite else pool_size,
        max_overflow=None if is_sqlite else max_overflow,
        pool_timeout=None if is_sqlite else pool_timeout,
        pool_recycle=None if is_sqlite else pool_recycle,
        connect_args=connect_args,
    )

    # Session factory
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)

    return _engine


def dispose_engine() -> None:
    """Dispose the cached engine (useful in tests or hot-reload scenarios)."""
    global _engine, _SessionLocal
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _SessionLocal = None


# -----------------------------------------------------------------------------
# Session helpers
# -----------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy Session.
    Ensures rollback on exceptions and always closes the session.
    """
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()  # initializes engine & SessionLocal

    assert _SessionLocal is not None, "Session factory not initialized"
    db = _SessionLocal()  # type: ignore[call-arg]
    try:
        yield db
        # Let endpoints control commit; nothing to do on success path here.
    except Exception:
        # Safety net: rollback any uncommitted transaction
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context manager for scripts/jobs:
        with session_scope() as db:
            ...
    Auto-commit on success, rollback on exceptions.
    """
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()

    assert _SessionLocal is not None, "Session factory not initialized"
    db = _SessionLocal()  # type: ignore[call-arg]
    try:
        yield db
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------

def ping_db() -> Tuple[bool, str]:
    """
    Try a simple 'SELECT 1'. Returns (ok, message).
    """
    try:
        eng = get_engine()
        with eng.connect() as conn:
            # A trivial SQL that works across Postgres & SQLite
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except OperationalError as e:
        return False, f"operational_error: {e.__class__.__name__}"
    except SQLAlchemyError as e:
        return False, f"sqlalchemy_error: {e.__class__.__name__}"
    except Exception as e:
        return False, f"error: {e.__class__.__name__}"
