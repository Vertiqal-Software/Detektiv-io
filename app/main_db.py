# app/main_db.py
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any, Tuple
from threading import Lock
import random  # noqa: F401
import time

import psycopg2  # uses psycopg2-binary from requirements
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Module logger
log = logging.getLogger(__name__)

# Engine state
_ENGINE: Optional[Engine] = None
_LAST_PARAMS: Optional[Tuple[Tuple[str, Any], ...]] = None
_LOCK = Lock()  # protect (re)builds across threads


def _get_env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except Exception:
        return default


def _current_params() -> Dict[str, Any]:
    """
    Build a psycopg2 connect() param dict directly from env.
    This bypasses URL parsing entirely (so passwords like 'OPqw1290@@.pgAdmin4'
    don't need any quoting/encoding).

    ADDITIVE features (all optional via env):
      - SSL extras: POSTGRES_SSLCERT, POSTGRES_SSLKEY, POSTGRES_SSLROOTCERT
      - Keepalives: POSTGRES_KEEPALIVES, *_IDLE, *_INTERVAL, *_COUNT
      - Application name: POSTGRES_APPLICATION_NAME
      - Statement timeout: POSTGRES_STATEMENT_TIMEOUT_MS (via 'options')
      - Search path: POSTGRES_SEARCH_PATH (via 'options')
      - Arbitrary options: POSTGRES_OPTIONS (appended to 'options')
    """
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")
    connect_timeout = _get_env_int("POSTGRES_CONNECT_TIMEOUT", 5)

    params: Dict[str, Any] = {
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),  # raw, no quoting needed
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": _get_env_int("POSTGRES_PORT", 5432),
        "dbname": os.getenv("POSTGRES_DB", "detecktiv"),
        "sslmode": sslmode,
        "connect_timeout": connect_timeout,
    }

    # SSL extras (psycopg2 params)
    for env_name, key in [
        ("POSTGRES_SSLCERT", "sslcert"),
        ("POSTGRES_SSLKEY", "sslkey"),
        ("POSTGRES_SSLROOTCERT", "sslrootcert"),
    ]:
        val = os.getenv(env_name)
        if val:
            params[key] = val

    # Keepalives (supported by libpq/psycopg2)
    for env_name, key in [
        ("POSTGRES_KEEPALIVES", "keepalives"),
        ("POSTGRES_KEEPALIVES_IDLE", "keepalives_idle"),
        ("POSTGRES_KEEPALIVES_INTERVAL", "keepalives_interval"),
        ("POSTGRES_KEEPALIVES_COUNT", "keepalives_count"),
    ]:
        val = os.getenv(env_name)
        if val is not None and val != "":
            # psycopg2 expects ints for these; fall back gracefully
            try:
                params[key] = int(val)
            except Exception:
                params[key] = val

    # Application name (helps in pg_stat_activity)
    app_name = os.getenv("POSTGRES_APPLICATION_NAME") or os.getenv("APP_NAME")
    if app_name:
        params["application_name"] = app_name

    # Options: statement_timeout, search_path, and raw POSTGRES_OPTIONS
    options_parts = []
    st_ms = os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS")
    if st_ms and st_ms.isdigit():
        options_parts.append(f"-c statement_timeout={st_ms}")
    search_path = os.getenv("POSTGRES_SEARCH_PATH")
    if search_path:
        options_parts.append(f"-c search_path={search_path}")
    raw_opts = os.getenv("POSTGRES_OPTIONS")
    if raw_opts:
        options_parts.append(raw_opts)
    if options_parts:
        params["options"] = " ".join(options_parts)

    return params


def _params_fingerprint(p: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    # stable ordering for comparison (tuples of sorted items)
    return tuple(sorted(p.items()))


def _masked_params(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of params with sensitive fields removed for safe logging.
    We *remove* password instead of assigning a string literal to avoid Bandit B105.
    """
    return {k: v for k, v in p.items() if k.lower() != "password"}


def dispose_engine_safely() -> None:
    """
    Dispose the current engine if present. Never raise; logs errors instead.
    Useful for tests or when you know env vars changed and you want a fresh engine.
    """
    global _ENGINE
    if _ENGINE is None:
        return
    try:
        _ENGINE.dispose()
    except Exception:
        log.exception("Engine dispose failed")
    finally:
        _ENGINE = None


def reset_engine() -> None:
    """
    Force a rebuild of the engine on next get_engine() call.
    Does not remove any logic; just clears cached state.
    """
    global _LAST_PARAMS
    dispose_engine_safely()
    _LAST_PARAMS = None


def ping_db() -> Tuple[bool, str]:
    """
    Quick connectivity check using psycopg2 directly (bypassing SQLAlchemy).
    Returns (ok, message). Does not leak secrets.
    """
    params = _current_params()
    try:
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                _ = cur.fetchone()
        return True, "ok"
    except Exception as e:
        log.warning("DB ping failed with params=%s error=%s", _masked_params(params), e)
        return False, str(e)


def ping_engine() -> Tuple[bool, str]:
    """
    Optional: ping using the SQLAlchemy Engine.
    """
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True, "ok"
    except Exception as e:
        log.warning("Engine ping failed: %s", e)
        return False, str(e)


def _build_engine(**kw) -> Engine:
    """
    Internal helper to build the Engine with env-driven pool settings.
    Uses a 'creator' that calls psycopg2.connect(**params) with retries/backoff.
    """
    params = _current_params()

    # Connection retries with exponential backoff (small defaults; env-tunable)
    retries = _get_env_int("DB_CONNECT_RETRIES", 3)
    backoff_ms = _get_env_int("DB_CONNECT_BACKOFF_MS", 200)

    def _creator():
        attempt = 0
        while True:
            attempt += 1
            try:
                return psycopg2.connect(**params)
            except Exception as e:
                if attempt >= max(1, retries):
                    # last attempt -> raise
                    log.warning(
                        "psycopg2.connect failed (attempt %s/%s) params=%s err=%s",
                        attempt,
                        retries,
                        _masked_params(params),
                        e,
                    )
                    raise
                # backoff with jitter
                delay = (backoff_ms * (2 ** (attempt - 1))) / 1000.0
                delay = delay * (0.9 + 0.2 * random.random())  # 10% jitter
                log.info(
                    "psycopg2.connect failed (attempt %s/%s), retrying in %.2fs ...",
                    attempt,
                    retries,
                    delay,
                )
                time.sleep(delay)

    # Pool settings (only applied if provided; otherwise use SQLAlchemy defaults)
    pool_kwargs: Dict[str, Any] = {}
    if os.getenv("SQLALCHEMY_POOL_SIZE"):
        pool_kwargs["pool_size"] = _get_env_int("SQLALCHEMY_POOL_SIZE", 5)
    if os.getenv("SQLALCHEMY_MAX_OVERFLOW"):
        pool_kwargs["max_overflow"] = _get_env_int("SQLALCHEMY_MAX_OVERFLOW", 10)
    if os.getenv("SQLALCHEMY_POOL_TIMEOUT"):
        pool_kwargs["pool_timeout"] = _get_env_int("SQLALCHEMY_POOL_TIMEOUT", 30)
    if os.getenv("SQLALCHEMY_POOL_RECYCLE"):
        pool_kwargs["pool_recycle"] = _get_env_int("SQLALCHEMY_POOL_RECYCLE", 1800)
    # echo SQL (debug aid)
    echo = os.getenv("SQLALCHEMY_ECHO", "0").lower() in ("1", "true", "yes")

    eng = create_engine(
        "postgresql+psycopg2://",
        future=True,
        pool_pre_ping=True,
        creator=_creator,
        echo=echo,
        **pool_kwargs,
    )
    log.info(
        "Engine constructed with params=%s pool=%s",
        _masked_params(params),
        {k: v for k, v in pool_kwargs.items()},
    )
    return eng


def get_engine() -> Engine:
    """
    Lazily (re)build a SQLAlchemy Engine using a custom creator that calls
    psycopg2.connect(**params). If env changes between tests/runs, the engine
    is rebuilt with the new parameters.
    """
    global _ENGINE, _LAST_PARAMS

    params = _current_params()
    fp = _params_fingerprint(params)

    # Fast path: engine exists with same params
    if _ENGINE is not None and _LAST_PARAMS == fp:
        return _ENGINE

    # Serialize creation/replace to avoid race conditions
    with _LOCK:
        # Re-check inside the lock to prevent double creation
        if _ENGINE is None or _LAST_PARAMS != fp:
            # Dispose the old engine (if any) before replacing it
            if _ENGINE is not None:
                try:
                    _ENGINE.dispose()
                except Exception:
                    log.exception("Engine dispose failed during rebuild")

            _ENGINE = _build_engine()
            _LAST_PARAMS = fp
            log.info("Engine (re)built with params=%s", _masked_params(params))

    return _ENGINE


def engine_pool_status() -> str:
    """
    Return a human-readable pool status string if available; else 'unknown'.
    """
    try:
        eng = get_engine()
        # Most SQLAlchemy pools implement .status() -> str
        status = getattr(eng.pool, "status", None)
        if callable(status):
            return status()
        return "unknown"
    except Exception as e:
        log.debug("engine_pool_status failed: %s", e)
        return "unknown"
