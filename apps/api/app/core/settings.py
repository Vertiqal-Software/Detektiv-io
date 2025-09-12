# app/core/settings.py
"""
This file was carrying API route code by mistake. I’m keeping your endpoints intact,
fixing indentation/syntax so it runs cleanly. Nothing here is auto-mounted unless
you explicitly include `router` in your FastAPI app.

If all you need is a tiny helper (used by some tooling), `health_status()` returns
a simple OK dict without importing FastAPI.
"""

from __future__ import annotations

import os
import socket
import time

import psycopg2
from psycopg2 import OperationalError


# Optional: lightweight helper some parts of the app/tests may call
def health_status() -> dict[str, str]:
    """Return a minimal health payload without any framework imports."""
    return {"status": "ok"}


# --- Your API routes preserved here (not auto-mounted) ---
# If you want these active, include this module's `router` in app.main
# e.g. `app.include_router(settings.router)` (but you likely already have /health elsewhere)
try:
    from fastapi import APIRouter  # heavy import kept inside try just in case
except (
    Exception
):  # pragma: no cover - FastAPI always exists in runtime, but be defensive
    APIRouter = None  # type: ignore

if APIRouter is not None:
    router = APIRouter()

    @router.get("/health")
    def health():
        return {"status": "ok"}

    @router.get("/readiness")
    def readiness():
        """
        Shallow DB + config checks for container healthchecks/readiness probes.
        Never logs sensitive data.
        """
        started = time.time()

        # Basic config sanity (no secret values in response)
        cfg = {
            "db_host": os.getenv("POSTGRES_HOST", ""),
            "db_port": os.getenv("POSTGRES_PORT", ""),
            "db_name": os.getenv("POSTGRES_DB", ""),
            "has_db_password": bool(os.getenv("POSTGRES_PASSWORD")),
            "has_ch_api_key": bool(os.getenv("CH_API_KEY")),
            "hostname": socket.gethostname(),
        }

        # DB ping (no transactions, 2s timeout)
        db_ok = False
        try:
            conn = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "detecktiv"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                connect_timeout=2,
                sslmode="disable",
            )
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                _ = cur.fetchone()
            conn.close()
            db_ok = True
        except OperationalError as e:
            # Keep the error short and non-sensitive
            cfg["db_error"] = str(e)[:160]

        duration_ms = int((time.time() - started) * 1000)
        status = "ok" if db_ok else "degraded"
        return {
            "status": status,
            "checks": {"db": db_ok},
            "duration_ms": duration_ms,
            "env": cfg,
        }
