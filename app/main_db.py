# app/main_db.py
from __future__ import annotations

import os
from typing import Optional, Dict, Any, Tuple

import psycopg2  # uses psycopg2-binary from requirements
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


_ENGINE: Optional[Engine] = None
_LAST_PARAMS: Optional[Tuple[Tuple[str, Any], ...]] = None


def _current_params() -> Dict[str, Any]:
    """
    Build a psycopg2 connect() param dict directly from env.
    This bypasses URL parsing entirely (so passwords like 'OPqw1290@@.pgAdmin4'
    don't need any quoting/encoding).
    """
    return {
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),  # raw, no quoting needed
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "detecktiv"),
        "sslmode": "disable",
    }


def _params_fingerprint(p: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    # stable ordering for comparison (tuples of sorted items)
    return tuple(sorted(p.items()))


def get_engine() -> Engine:
    """
    Lazily (re)build a SQLAlchemy Engine using a custom creator that calls
    psycopg2.connect(**params). If env changes between tests/runs, the engine
    is rebuilt with the new parameters.
    """
    global _ENGINE, _LAST_PARAMS

    params = _current_params()
    fp = _params_fingerprint(params)

    if _ENGINE is None or _LAST_PARAMS != fp:
        # Dispose the old engine (if any) before replacing it
        if _ENGINE is not None:
            try:
                _ENGINE.dispose()
            except Exception:
                pass

        def _creator():
            return psycopg2.connect(**params)

        # Empty URL + creator lets us skip URL quoting entirely.
        _ENGINE = create_engine(
            "postgresql+psycopg2://",
            future=True,
            pool_pre_ping=True,
            creator=_creator,
        )
        _LAST_PARAMS = fp

    return _ENGINE
