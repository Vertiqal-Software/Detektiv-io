# app/logging_setup.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict
from fastapi import FastAPI, Request


class JSONFormatter(logging.Formatter):
    """
    Lightweight JSON formatter for production logs.
    Includes request_id if present, avoids leaking secrets.
    """

    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "ts": int(time.time() * 1000),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Attach common extras if they exist
        for k in (
            "request_id",
            "path",
            "method",
            "status_code",
            "duration_ms",
            "client_ip",
        ):
            if hasattr(record, k):
                base[k] = getattr(record, k)

        # Attach error info if present
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(base, separators=(",", ":"))


def setup_logging() -> None:
    """
    Configure root logging once. Uvicorn's own access logger is noisy;
    we prefer our own access middleware below.
    """
    if getattr(setup_logging, "_configured", False):  # type: ignore[attr-defined]
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Tame chatty libs
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("urllib3").setLevel("WARNING")

    setattr(setup_logging, "_configured", True)  # type: ignore[attr-defined]


def _client_ip_from_scope(scope: Dict[str, Any]) -> str:
    # Try X-Forwarded-For when behind a proxy (if your ingress sets it)
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if isinstance(client, (list, tuple)) and client else "unknown"


def install_access_logger(app: FastAPI) -> None:
    """
    Add a middleware that emits JSON access logs with:
      method, path, status_code, duration_ms, request_id, client_ip.
    Does NOT log query strings or headers to avoid leaking secrets.
    """
    logger = logging.getLogger("access")

    @app.middleware("http")
    async def _access_log(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        req_id = response.headers.get("x-request-id") or request.headers.get(
            "x-request-id"
        )
        if not req_id:
            # Last resort: don't generate a new one here (main.py already sets it)
            req_id = "-"

        extra = {
            "request_id": req_id,
            "method": request.method,
            "path": request.url.path,  # path only (no query string)
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": _client_ip_from_scope(request.scope),
        }

        # Use 'extra' to attach fields into the LogRecord
        logger.info("request", extra=extra)
        return response
