# app/api/health.py
from fastapi import APIRouter
import os
import socket
import time
import psycopg2
from psycopg2 import OperationalError

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    # simple liveness
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
            sslmode=os.getenv("POSTGRES_SSLMODE", "disable"),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            _ = cur.fetchone()
        conn.close()
        db_ok = True
    except OperationalError as e:
        cfg["db_error"] = str(e)[:160]

    duration_ms = int((time.time() - started) * 1000)
    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "checks": {"db": db_ok},
        "duration_ms": duration_ms,
        "env": cfg,
    }
