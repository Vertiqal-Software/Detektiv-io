# app/api/health.py
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Response
import os
import socket
import time
from contextlib import closing
from urllib.parse import urlparse, parse_qs

# ---------- Optional PG drivers (we support Postgres and SQLite) ----------
try:
    import psycopg2  # type: ignore
    from psycopg2 import OperationalError as PGOperationalError  # type: ignore

    _PG_DRIVER = "psycopg2"
except Exception:  # pragma: no cover
    try:
        import psycopg  # type: ignore
        from psycopg import OperationalError as PGOperationalError  # type: ignore

        _PG_DRIVER = "psycopg"
    except Exception:  # pragma: no cover
        psycopg2 = None  # type: ignore
        psycopg = None  # type: ignore
        PGOperationalError = Exception  # type: ignore
        _PG_DRIVER = "none"

# SQLite is in the stdlib
import sqlite3

# ---------- Optional Companies House client for readiness ----------
try:  # pragma: no cover
    from app.services.companies_house import CompaniesHouseClient, CompaniesHouseError  # type: ignore
except Exception:  # pragma: no cover
    CompaniesHouseClient = None  # type: ignore
    CompaniesHouseError = RuntimeError  # type: ignore

router = APIRouter(tags=["Health"])


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on", "y"}


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
    """
    HEAD variant for lightweight probes.
    Preserve headers set by health() instead of returning a new Response.
    """
    _ = health(request, response)
    response.status_code = 200
    return response


# Common alias used by some platforms
@router.get("/healthz")
def healthz(request: Request, response: Response) -> Dict[str, str]:
    return health(request, response)


# ---------------------------------------------------------------------------
# DB connection params (supports Postgres and SQLite)
# ---------------------------------------------------------------------------


def _db_params_from_env() -> Dict[str, Any]:
    """
    Build connection params for a quick health ping.

    Priority:
      1) DATABASE_URL: postgres*, sqlite*
      2) POSTGRES_* envs (Postgres only)

    Returns a dict with a "kind" key:
      - {"kind":"postgres", ...pg connect kwargs..., "_source": "...", "_scheme": "..."}
      - {"kind":"sqlite", "database": "<file or :memory:>", "_source": "...", "_scheme": "sqlite"}
    """
    connect_timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2"))

    raw_url = (os.getenv("DATABASE_URL") or "").strip()
    if raw_url:
        p = urlparse(raw_url)
        scheme = (p.scheme or "").lower()

        # --- Postgres URL ---
        if scheme.startswith("postgres"):
            q = parse_qs(p.query or "")
            sslmode = (
                q.get("sslmode", [os.getenv("POSTGRES_SSLMODE", "disable")])[0]
            ) or "disable"
            return {
                "kind": "postgres",
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

        # --- SQLite URL ---
        if scheme.startswith("sqlite"):
            # urlparse gives path like "/./test.db" — strip a single leading slash
            db_path = (p.path or "").lstrip("/") or ":memory:"
            return {
                "kind": "sqlite",
                "database": db_path,
                "_source": "DATABASE_URL",
                "_scheme": scheme,
            }

    # Fallback to discrete POSTGRES_* vars (no SQLite in this branch)
    return {
        "kind": "postgres",
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


def _pg_quick_ping(connect_kwargs: Dict[str, Any]) -> bool:
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
    except PGOperationalError:
        return False
    except Exception:
        return False


def _sqlite_quick_ping(database: str) -> bool:
    """
    Minimal 'SELECT 1' for SQLite databases.
    Returns True on success, False on failure.
    """
    try:
        # uri=False here because we already parsed a path
        with closing(sqlite3.connect(database, timeout=1.0)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Optional Companies House check (fast search)
# ---------------------------------------------------------------------------


def _ch_quick_ping() -> bool:
    """
    Quick smoke-check for Companies House:
    - Requires CH_API_KEY (or COMPANIES_HOUSE_API_KEY).
    - Uses /search/companies?q=test&items_per_page=1
    - Returns True on 200 OK with valid JSON; False otherwise.
    """
    if CompaniesHouseClient is None:
        return False
    # Require an API key; if absent, treat as failure (we don't want false positives)
    if not (os.getenv("CH_API_KEY") or os.getenv("COMPANIES_HOUSE_API_KEY")):
        return False
    try:
        cli = CompaniesHouseClient()
        data = cli.search_companies("test", items_per_page=1, start_index=0)
        # best-effort close without assuming sync/async interface
        try:
            close = getattr(cli, "close", None)
            aclose = getattr(cli, "aclose", None)
            if callable(close):
                close()
            elif callable(aclose):
                # don't await in sync context; just ignore
                pass
        except Exception:
            pass
        return isinstance(data, dict)
    except CompaniesHouseError:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@router.get("/readiness")
def readiness(request: Request, response: Response) -> Dict[str, Any]:
    """
    Shallow DB + optional upstream checks for container healthchecks/readiness probes.
    Never logs sensitive data. Keeps error messages short and non-leaky.

    Env flags:
      - HEALTH_SKIP_DB_CHECK=1        → skip DB ping
      - HEALTH_CHECK_CH=1             → include Companies House quick check
      - HEALTH_CHECK_CH_REQUIRED=1    → if CH check fails, readiness is degraded
      - READINESS_HTTP_503_ON_FAIL=1  → set HTTP 503 when status != ok
    """
    started = time.time()

    # Echo request id and prevent caching of health responses
    rid = request.headers.get("x-request-id")
    if rid:
        response.headers["x-request-id"] = rid
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Service", "detecktiv-io")

    params = _db_params_from_env()
    scheme = str(params.get("_scheme", ""))
    kind = str(params.get("kind", "postgres"))

    # Basic config sanity (strings only; no secrets)
    cfg: Dict[str, Any] = {
        "db_host": str(params.get("host", "")) if kind == "postgres" else "",
        "db_port": str(params.get("port", "")) if kind == "postgres" else "",
        "db_name": (
            str(params.get("dbname", ""))
            if kind == "postgres"
            else str(params.get("database", ""))
        ),
        "db_url_source": str(params.get("_source", "")),
        "db_scheme": scheme or ("postgresql" if kind == "postgres" else "sqlite"),
        "pg_driver": _PG_DRIVER if kind == "postgres" else None,
        "has_db_password": bool(
            os.getenv("POSTGRES_PASSWORD")
            or (
                urlparse(os.getenv("DATABASE_URL", "")).password
                if kind == "postgres"
                else False
            )
        ),
        "has_ch_api_key": bool(
            os.getenv("CH_API_KEY") or os.getenv("COMPANIES_HOUSE_API_KEY")
        ),
        "hostname": socket.gethostname(),
    }

    # --- DB check ---
    skip_db = _env_bool("HEALTH_SKIP_DB_CHECK", False)
    if skip_db:
        db_ok = True
    else:
        if kind == "postgres":
            db_ok = _pg_quick_ping(params)
        else:  # sqlite
            db_ok = _sqlite_quick_ping(str(params.get("database", ":memory:")))
    if not db_ok:
        # Short error marker; keep opaque to avoid leaking infra details
        cfg["db_error"] = "unreachable-or-no-driver"

    # --- Companies House check (optional) ---
    ch_check_enabled = _env_bool("HEALTH_CHECK_CH", False)
    ch_ok: Optional[bool] = None
    if ch_check_enabled:
        ch_ok = _ch_quick_ping()
        cfg["ch_checked"] = True
        cfg["ch_ok"] = ch_ok

    # status
    status_ok = db_ok
    if ch_check_enabled and _env_bool("HEALTH_CHECK_CH_REQUIRED", False):
        status_ok = status_ok and bool(ch_ok)

    duration_ms = int((time.time() - started) * 1000)
    status = "ok" if status_ok else "degraded"

    # Optional: return 503 on failure (default stays 200 to preserve existing behaviour)
    if not status_ok and _env_bool("READINESS_HTTP_503_ON_FAIL", False):
        response.status_code = 503

    # Optional version info
    version = (
        os.getenv("APP_VERSION")
        or os.getenv("COMMIT_SHA")
        or os.getenv("RELEASE")
        or "unknown"
    )

    checks: Dict[str, Any] = {"db": db_ok}
    if ch_check_enabled:
        checks["companies_house"] = bool(ch_ok)

    return {
        "status": status,
        "checks": checks,
        "duration_ms": duration_ms,
        "version": version,
        "env": cfg,
    }


@router.head("/readiness")
def readiness_head(request: Request, response: Response) -> Response:
    """
    HEAD variant for lightweight probes.

    Preserve headers set by readiness() and return 200 or 503 depending on status
    (the latter only if READINESS_HTTP_503_ON_FAIL=1).
    """
    body = readiness(request, response)
    # If we didn't set 503 in readiness(), keep 200
    if body.get("status") != "ok" and _env_bool("READINESS_HTTP_503_ON_FAIL", False):
        response.status_code = 503
    else:
        response.status_code = 200
    return response


# Common alias used by some platforms
@router.get("/ready")
def ready(request: Request, response: Response) -> Dict[str, Any]:
    return readiness(request, response)


__all__ = [
    "router",
    "health",
    "health_head",
    "healthz",
    "readiness",
    "readiness_head",
    "ready",
]
