# app/api/health.py
from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Request, Response
import os
import socket
import time
from contextlib import closing
from urllib.parse import urlparse, parse_qs

# Prefer psycopg2; fall back to psycopg (v3) if needed
try:
    import psycopg2  # type: ignore
    from psycopg2 import OperationalError  # type: ignore

    _PG_DRIVER = "psycopg2"
except Exception:  # pragma: no cover
    try:
        import psycopg  # type: ignore
        from psycopg import OperationalError  # type: ignore

        _PG_DRIVER = "psycopg"
    except Exception:  # pragma: no cover
        psycopg2 = None  # type: ignore
        psycopg = None  # type: ignore
        OperationalError = Exception  # type: ignore
        _PG_DRIVER = "none"

router = APIRouter(tags=["Health"])


@router.get("/health")
def health(request: Request, response: Response) -> Dict[str, str]:
    """
    Simple liveness.
    Adds x-request-id echo and no-store cache header for safety.
    """
    rid = request.headers.get("x-request-id")
    if rid:
        response.headers["x-request-id"] = rid
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Service", "detecktiv-io")
    return {"status": "ok"}


@router.head("/health")
def health_head(request: Request, response: Response) -> Response:
    """HEAD variant for lightweight probes."""
    _ = health(request, response)
    return Response(status_code=200)


# Common alias used by some platforms
@router.get("/healthz")
def healthz(request: Request, response: Response) -> Dict[str, str]:
    return health(request, response)


def _db_params_from_env() -> Dict[str, Any]:
    """
    Build psycopg connect kwargs from env.
    Priority: DATABASE_URL (postgres*) -> POSTGRES_* variables.
    Never logs secrets; caller must avoid printing the returned dict.
    """
    connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2"))

    raw_url = os.getenv("DATABASE_URL", "")
    if raw_url:
        p = urlparse(raw_url)
        scheme = (p.scheme or "").lower()
        if scheme.startswith("postgres"):
            q = parse_qs(p.query or "")
            sslmode = (
                q.get("sslmode", [os.getenv("POSTGRES_SSLMODE", "disable")])[0]
            ) or "disable"
            return {
                "dbname": (p.path or "/").lstrip("/")
                or os.getenv("POSTGRES_DB", "detecktiv"),
                "user": p.username or os.getenv("POSTGRES_USER", "postgres"),
                "password": p.password or os.getenv("POSTGRES_PASSWORD", ""),
                "host": p.hostname or os.getenv("POSTGRES_HOST", "127.0.0.1"),
                "port": int(p.port or int(os.getenv("POSTGRES_PORT", "5432"))),
                "sslmode": sslmode,
                "connect_timeout": connect_timeout,
                "_source": "DATABASE_URL",
                "_scheme": scheme,
            }

    # Fallback to discrete POSTGRES_* vars
    return {
        "dbname": os.getenv("POSTGRES_DB", "detecktiv"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "sslmode": os.getenv("POSTGRES_SSLMODE", "disable"),
        "connect_timeout": connect_timeout,
        "_source": "POSTGRES_*",
        "_scheme": "postgresql",
    }


def _db_quick_ping(connect_kwargs: Dict[str, Any]) -> bool:
    """
    Minimal 'SELECT 1' using whichever PG driver is available.
    Returns True on success, False on failure. Does NOT leak secrets.
    """
    # Strip meta keys
    kw = {k: v for k, v in connect_kwargs.items() if not k.startswith("_")}
    try:
        if _PG_DRIVER == "psycopg2" and psycopg2:
            with closing(psycopg2.connect(**kw)) as conn:  # type: ignore[arg-type]
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    _ = cur.fetchone()
            return True
        elif _PG_DRIVER == "psycopg" and psycopg:
            with closing(psycopg.connect(**kw)) as conn:  # type: ignore[attr-defined]
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    _ = cur.fetchone()
            return True
        else:
            # No driver installed
            return False
    except OperationalError:
        return False
    except Exception:
        return False


@router.get("/readiness")
def readiness(request: Request, response: Response) -> Dict[str, Any]:
    """
    Shallow DB + config checks for container healthchecks/readiness probes.
    Never logs sensitive data. Keeps error messages short and non-leaky.

    Set HEALTH_SKIP_DB_CHECK=1 to skip the DB ping (useful in CI or when DB is optional).
    """
    started = time.time()

    # Echo request id and prevent caching of health responses
    rid = request.headers.get("x-request-id")
    if rid:
        response.headers["x-request-id"] = rid
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Service", "detecktiv-io")

    params = _db_params_from_env()

    # Basic config sanity (strings only; no secrets)
    cfg = {
        "db_host": str(params.get("host", "")),
        "db_port": str(params.get("port", "")),
        "db_name": str(params.get("dbname", "")),
        "db_url_source": str(params.get("_source", "")),
        "db_scheme": str(params.get("_scheme", "")),
        "pg_driver": _PG_DRIVER,
        "has_db_password": bool(
            os.getenv("POSTGRES_PASSWORD")
            or urlparse(os.getenv("DATABASE_URL", "")).password
        ),
        "has_ch_api_key": bool(
            os.getenv("CH_API_KEY") or os.getenv("COMPANIES_HOUSE_API_KEY")
        ),
        "hostname": socket.gethostname(),
    }

    skip_db = (os.getenv("HEALTH_SKIP_DB_CHECK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }

    db_ok = True if skip_db else _db_quick_ping(params)
    if not db_ok:
        # Short error marker; keep opaque to avoid leaking infra details
        cfg["db_error"] = "unreachable-or-no-driver"

    duration_ms = int((time.time() - started) * 1000)
    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "checks": {"db": db_ok},
        "duration_ms": duration_ms,
        "env": cfg,
    }


@router.head("/readiness")
def readiness_head(request: Request, response: Response) -> Response:
    """HEAD variant for lightweight probes."""
    body = readiness(request, response)
    return Response(status_code=200 if body.get("status") == "ok" else 503)


# Common alias used by some platforms
@router.get("/ready")
def ready(request: Request, response: Response) -> Dict[str, Any]:
    return readiness(request, response)
