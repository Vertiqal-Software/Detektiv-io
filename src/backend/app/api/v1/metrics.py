# app/api/metrics.py
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import APIRouter, Response, Request, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, CollectorRegistry
from prometheus_client import multiprocess

router = APIRouter(tags=["metrics"])

_security = HTTPBasic(auto_error=False)  # enforce only if env is set


def _enabled() -> bool:
    """Toggle via METRICS_ENABLED=1|0 (defaults to enabled)."""
    return (os.getenv("METRICS_ENABLED") or "1").strip() in {"1", "true", "yes", "on"}


def _require_metrics_auth_if_configured(
    creds: Optional[HTTPBasicCredentials] = Depends(_security),
) -> None:
    """
    If METRICS_USERNAME and METRICS_PASSWORD are set, require HTTP Basic auth.
    Otherwise, no-op (metrics remain publicly readable, as before).
    """
    user = os.getenv("METRICS_USERNAME")
    pwd = os.getenv("METRICS_PASSWORD")
    if not user and not pwd:
        return  # auth not configured

    # Auth configured -> enforce
    if not creds:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )

    if not (
        secrets.compare_digest(creds.username or "", user or "")
        and secrets.compare_digest(creds.password or "", pwd or "")
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )


@router.get("/metrics")
def metrics(
    request: Request,
    response: Response,
    _: None = Depends(_require_metrics_auth_if_configured),
):
    """
    Expose Prometheus metrics.
    - Honors multiprocess mode if configured (PROMETHEUS_MULTIPROC_DIR).
    - Optional HTTP Basic auth via METRICS_USERNAME/METRICS_PASSWORD.
    - Echoes x-request-id and sets Cache-Control: no-store.
    - Disabled cleanly when METRICS_ENABLED=0 (returns 404).
    """
    # Disabled? Return 404 (less discoverable than 503)
    if not _enabled():
        return Response(status_code=404)

    # Echo request id and discourage caches
    rid = request.headers.get("x-request-id")
    if rid:
        response.headers["x-request-id"] = rid
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Service", "detecktiv-io")

    registry = CollectorRegistry()
    # Works with or without multiprocess mode
    try:
        multiprocess.MultiProcessCollector(registry)  # no-op if not configured
    except Exception:  # nosec B110
        pass

    try:
        data = generate_latest(registry)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST, headers=response.headers)
    except Exception:
        # Defensive: emit a simple 500 with plaintext body if generation fails
        return Response(
            status_code=500,
            content=b"internal error generating metrics",
            media_type="text/plain; charset=utf-8",
            headers=response.headers,  # keep x-request-id + no-store
        )


@router.head("/metrics")
def metrics_head(
    request: Request,
    response: Response,
    _: None = Depends(_require_metrics_auth_if_configured),
) -> Response:
    """
    Lightweight HEAD endpoint for probes that only need headers/status.
    Mirrors enablement/auth of GET /metrics.
    """
    if not _enabled():
        return Response(status_code=404)

    # Mirror headers from GET /metrics
    rid = request.headers.get("x-request-id")
    if rid:
        response.headers["x-request-id"] = rid
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Service", "detecktiv-io")
    response.status_code = 200
    return response
