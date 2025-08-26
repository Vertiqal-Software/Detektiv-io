# app/main_db.py
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any, Tuple
from threading import Lock

import psycopg2  # uses psycopg2-binary from requirements
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Module logger (safe to import before app logging config; handlers can be set elsewhere)
log = logging.getLogger(__name__)

# Engine state
_ENGINE: Optional[Engine] = None
_LAST_PARAMS: Optional[Tuple[Tuple[str, Any], ...]] = None
_LOCK = Lock()  # protect (re)builds across threads


def _current_params() -> Dict[str, Any]:
    """
    Build a psycopg2 connect() param dict directly from env.
    This bypasses URL parsing entirely (so passwords like 'OPqw1290@@.pgAdmin4'
    don't need any quoting/encoding).
    """
    # Allow optional overrides via env, keep safe defaults
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")
    connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))

    return {
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),  # raw, no quoting needed
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "detecktiv"),
        "sslmode": sslmode,
        "connect_timeout": connect_timeout,
    }


def _params_fingerprint(p: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    # stable ordering for comparison (tuples of sorted items)
    return tuple(sorted(p.items()))


def _masked_params(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of params with sensitive fields removed for safe logging.
    We *remove* password instead of assigning a string literal to avoid Bandit B105.
    """
    # lower() guard just in case the key casing varies in future
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
        # Bandit B110 fix: do not silently swallow exceptions
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
        # Don't include password in logs
        log.warning("DB ping failed with params=%s error=%s", _masked_params(params), e)
        return False, str(e)


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
                    # Bandit B110 fix: never silently swallow exceptions
                    log.exception("Engine dispose failed during rebuild")

            def _creator():
                # Use psycopg2 with our already-built dict to avoid URL quoting issues
                return psycopg2.connect(**params)

            # Empty URL + creator lets us skip URL quoting entirely.
            _ENGINE = create_engine(
                "postgresql+psycopg2://",
                future=True,
                pool_pre_ping=True,
                creator=_creator,
            )
            _LAST_PARAMS = fp
            log.info("Engine (re)built with params=%s", _masked_params(params))

    return _ENGINE
