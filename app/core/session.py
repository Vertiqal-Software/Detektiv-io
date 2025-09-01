# app/core/session.py
"""
Session factory for application code and quick scripts.

Features:
- Uses DATABASE_URL if provided, otherwise constructs a Postgres URL
  from POSTGRES_* environment variables.
- Auto-loads a .env file into the current process if DATABASE_URL/POSTGRES_* are missing.
  (Respects existing environment; does not overwrite variables already set.)
- Forces search_path to "<POSTGRES_SCHEMA or 'app'>, public" on every connection:
    * via psycopg2 connect args (options)
    * via on-connect event
    * via on-checkout event (applies to pooled connections)
- Exposes:
    - engine
    - SessionLocal
    - get_session() -> context manager yielding a Session
    - get_db() -> FastAPI dependency yielding a Session (with rollback/close)

Additive non-breaking enhancements:
- Normalize DATABASE_URL driver (e.g., 'postgres://' -> 'postgresql+psycopg2://').
- Pool tuning via env: DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE.
- Optional statement timeout and application name via env:
    * STATEMENT_TIMEOUT_MS (e.g., 30000)
    * POSTGRES_APP_NAME or APP_NAME
- Safer debug prints and URL masking.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional, Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session


def _maybe_load_dotenv() -> None:
    """
    Minimal .env loader (no external dependency).
    - Only loads if critical DB settings are not present.
    - Does not override variables already in the environment.
    - Supports simple KEY=VALUE lines; ignores comments and blank lines.
    """
    needed = [
        "DATABASE_URL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
    ]
    if any(os.getenv(k) for k in needed):
        return  # something is already set; skip loading

    env_file = os.getenv("ENV_FILE") or ".env"
    if not os.path.isfile(env_file):
        return

    try:
        with open(env_file, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                # strip optional quotes
                v = val.strip().strip('"').strip("'")
                # do not overwrite if already set
                if not os.getenv(key):
                    os.environ[key] = v
    except Exception:
        # Best-effort; fail silently so app can still run with existing env
        pass


def _mask_dsn(url: str) -> str:
    # mask password in DSN for optional debug output
    try:
        if "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        if "@" not in rest:
            return url
        auth, tail = rest.split("@", 1)
        if ":" in auth:
            user, _pwd = auth.split(":", 1)
            auth_masked = f"{user}:***"
        else:
            auth_masked = auth
        return f"{scheme}://{auth_masked}@{tail}"
    except Exception:
        return url


def _normalize_driver(url: str) -> str:
    """
    Ensure DSN uses an explicit driver when a generic scheme is used.
    - postgres://...           -> postgresql+psycopg2://...
    - postgresql://...         -> postgresql+psycopg2://...
    - already has +driver      -> leave unchanged
    """
    try:
        if "+psycopg2" in url or "+psycopg" in url or "+asyncpg" in url:
            return url
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://") :]
        return url
    except Exception:
        return url


def _append_query_param(url: str, key: str, value: Optional[str]) -> str:
    """
    Append a query parameter to the URL (simple string manip to avoid urllib re-encoding).
    """
    if not value:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={value}"


def _build_database_url_from_env() -> Optional[str]:
    url = os.getenv("DATABASE_URL")
    if url:
        return _normalize_driver(url)

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    sslmode = os.getenv("POSTGRES_SSLMODE")  # e.g., "disable"

    if not all([user, host, port, db]):
        return None

    # Percent-encode user/pass in case they contain special characters
    from urllib.parse import quote_plus as _qp

    user_enc = _qp(user)
    auth = user_enc
    if password is not None:
        auth = f"{user_enc}:{_qp(password)}"

    query = f"?sslmode={sslmode}" if sslmode else ""
    url = f"postgresql+psycopg2://{auth}@{host}:{port}/{db}{query}"
    return _normalize_driver(url)


def _make_engine() -> Engine:
    # Ensure env is populated, if possible
    _maybe_load_dotenv()

    url = _build_database_url_from_env()
    if not url:
        raise RuntimeError(
            "Database configuration is missing. Set DATABASE_URL or POSTGRES_* "
            "(POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB)."
        )

    schema = (os.getenv("POSTGRES_SCHEMA") or "app").strip() or "app"
    debug = os.getenv("SESSION_DEBUG") == "1"

    # Optional connection decorations
    app_name = os.getenv("POSTGRES_APP_NAME") or os.getenv("APP_NAME") or "detecktiv-io"
    stmt_timeout_ms = os.getenv("STATEMENT_TIMEOUT_MS")  # e.g., "30000"

    # Pool tuning (safe defaults)
    pool_size = int(os.getenv("DB_POOL_SIZE", "5") or "5")
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10") or "10")
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30") or "30")
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800") or "1800")  # seconds
    echo_sql = (os.getenv("DB_ECHO") == "1") or (os.getenv("SESSION_ECHO_SQL") == "1")

    # Add application_name to DSN query (non-breaking)
    url = _append_query_param(url, "application_name", app_name)

    if debug:
        print(f"[session] Using DB URL: {_mask_dsn(url)}")
        print(f"[session] Desired search_path: {schema},public")
        if stmt_timeout_ms:
            print(f"[session] Desired statement_timeout: {stmt_timeout_ms} ms")
        print(
            f"[session] Pool: size={pool_size} max_overflow={max_overflow} "
            f"timeout={pool_timeout}s recycle={pool_recycle}s echo={echo_sql}"
        )

    # psycopg2/psycopg drivers support 'options' which can set startup params
    options_parts = [f"-c search_path={schema},public"]
    if stmt_timeout_ms:
        options_parts.append(f"-c statement_timeout={stmt_timeout_ms}")
    connect_args = {}
    if url.startswith("postgresql"):
        connect_args["options"] = " ".join(options_parts)

    engine = create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,  # works with psycopg2/psycopg
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=echo_sql,
    )

    # Ensure schema exists and set session parameters when a new DB-API conn opens
    @event.listens_for(engine, "connect")
    def _set_params_on_connect(dbapi_conn, conn_record):  # type: ignore[no-redef]
        try:
            with dbapi_conn.cursor() as cur:
                # Create schema if not exists (non-fatal if insufficient privilege)
                try:
                    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                except Exception:
                    pass
                cur.execute(f"SET search_path TO {schema}, public")
                if stmt_timeout_ms:
                    cur.execute(f"SET statement_timeout TO {int(stmt_timeout_ms)}")
                # Set application_name at runtime as well (DSN already carries it)
                if app_name:
                    try:
                        cur.execute("SET application_name TO %s", [app_name])
                    except Exception:
                        pass
        except Exception:
            # Non-fatal
            pass

    # Re-assert key params when connection is checked out from pool
    @event.listens_for(engine, "checkout")
    def _set_params_on_checkout(dbapi_conn, conn_record, proxy):  # type: ignore[no-redef]
        try:
            with dbapi_conn.cursor() as cur:
                cur.execute(f"SET search_path TO {schema}, public")
                if stmt_timeout_ms:
                    cur.execute(f"SET statement_timeout TO {int(stmt_timeout_ms)}")
        except Exception:
            pass

    if debug:
        # One-time sanity check at engine creation
        try:
            from sqlalchemy import text as _text

            with engine.connect() as conn:
                sp = conn.execute(_text("SHOW search_path")).scalar_one()
                try:
                    st = conn.execute(_text("SHOW statement_timeout")).scalar_one()
                except Exception:
                    st = "(not supported)"
            print(f"[session] Engine check search_path={sp}; statement_timeout={st}")
        except Exception as e:
            print(f"[session] search_path/timeout check failed: {e}")

    return engine


engine: Engine = _make_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Context manager yielding a SQLAlchemy Session.
    Ensures proper close/rollback on error.
    """
    session: Session = SessionLocal()
    try:
        if os.getenv("SESSION_DEBUG") == "1":
            try:
                sp = session.execute(text("SHOW search_path")).scalar_one()
                print(f"[session] Session search_path={sp}")
            except Exception:
                pass
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a Session and guarantees rollback/close.
    """
    db: Session = SessionLocal()
    try:
        if os.getenv("SESSION_DEBUG") == "1":
            try:
                sp = db.execute(text("SHOW search_path")).scalar_one()
                print(f"[session] Dependency search_path={sp}")
            except Exception:
                pass
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
