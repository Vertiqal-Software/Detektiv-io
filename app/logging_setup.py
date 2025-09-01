# app/logging_setup.py
from __future__ import annotations

import json
import logging
import os
import re
import time
import contextvars
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request

# Context var so any log within a request can include the same request_id
_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def _scrub_message(msg: str) -> str:
    """
    Best-effort secret scrubbing for log messages.
    Targets common tokens: password, token, secret, api_key, authorization (Bearer).
    Kept conservative to avoid mangling arbitrary text.
    """
    try:
        if not msg:
            return msg

        # Bearer <token>  -> Bearer ***
        msg = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._-]+", "Bearer ***", msg)

        # key=value and key: value variants for common sensitive keys
        msg = re.sub(
            r"(?i)\b(password|token|secret|api[_-]?key|authorization)\s*[:=]\s*([^\s,;]+)",
            r"\1=***",
            msg,
        )

        # JSON-ish "key": "value" for those sensitive keys
        msg = re.sub(
            r'(?i)("(?:password|token|secret|api[_-]?key|authorization)"\s*:\s*")([^"]+)(")',
            r"\1***\3",
            msg,
        )
        return msg
    except Exception:
        # Never let scrubbing break logging
        return msg


class JSONFormatter(logging.Formatter):
    """
    Lightweight JSON formatter for production logs.
    Includes request_id if present, avoids leaking secrets.
    Optional envs:
      - LOG_SCRUB_SECRETS=1 (default): scrub sensitive tokens
      - LOG_TS_ISO=1: include 'ts_iso' in addition to 'ts' (epoch ms)
      - APP_NAME: adds 'service' field (e.g., detecktiv-io)
    """

    def format(self, record: logging.LogRecord) -> str:
        scrub = os.getenv("LOG_SCRUB_SECRETS", "1") == "1"
        ts_ms = int(time.time() * 1000)
        base: Dict[str, Any] = {
            "ts": ts_ms,
            "level": record.levelname,
            "logger": record.name,
        }

        # Optional service name
        app_name = os.getenv("APP_NAME")
        if app_name:
            base["service"] = app_name

        # compute message (respecting % formatting), then optionally scrub
        msg = record.getMessage()
        if scrub and isinstance(msg, str):
            msg = _scrub_message(msg)
        base["msg"] = msg

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

        # Attach error info if present (scrub if enabled)
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            if scrub and isinstance(exc_text, str):
                exc_text = _scrub_message(exc_text)
            base["exc_info"] = exc_text

        if os.getenv("LOG_TS_ISO", "0") == "1":
            # Add ISO timestamp alongside epoch ms
            base["ts_iso"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms / 1000)
            )

        return json.dumps(base, separators=(",", ":"))


class PrettyFormatter(logging.Formatter):
    """
    Human-friendly console formatter for local dev.
    Enabled with LOG_FORMAT=pretty (or LOG_FORMAT=plain as an alias).
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime())
        rid = getattr(record, "request_id", "-")
        msg = record.getMessage()
        return f"[{ts}] {record.levelname:<7} {record.name} rid={rid} :: {msg}"


class ContextInjectFilter(logging.Filter):
    """
    Injects request_id from contextvars into the record if not already present.
    Ensures any logger under a request emits a consistent request_id.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            rid = _request_id_ctx.get()
            if rid is not None:
                record.request_id = rid
        return True


def setup_logging() -> None:
    """
    Configure root logging once. Uvicorn's own access logger is noisy;
    we prefer our own access middleware below.
    Env:
      - LOG_LEVEL=INFO|DEBUG|...
      - LOG_FORMAT=json|pretty|plain  (default json)
      - LOG_SCRUB_SECRETS=1/0         (default 1)
      - LOG_TS_ISO=1/0                (default 0)
      - APP_NAME=...                  (optional service name field)
    """
    if getattr(setup_logging, "_configured", False):  # type: ignore[attr-defined]
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    if log_format == "plain":  # alias for pretty
        log_format = "pretty"

    handler = logging.StreamHandler()
    handler.addFilter(ContextInjectFilter())

    if log_format == "pretty":
        handler.setFormatter(PrettyFormatter())
    else:
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


def configure_uvicorn_logger_levels(app_level: Optional[str] = None) -> None:
    """
    Optional helper if you want to align uvicorn.* logger level with your app.
    Use like: configure_uvicorn_logger_levels(logging.getLogger().level)
    """
    level = app_level or logging.getLogger().level
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel("WARNING")


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
    Add a middleware that emits JSON (or pretty) access logs with:
      method, path, status_code, duration_ms, request_id, client_ip.
    Does NOT log query strings or headers to avoid leaking secrets.
    Also sets a contextvar so downstream logs include request_id automatically.

    Idempotent: calling this multiple times will not add duplicate middleware.
    """
    # Prevent double-install when reloads or duplicate imports occur
    if getattr(app.state, "access_logger_installed", False):
        return
    setattr(app.state, "access_logger_installed", True)

    logger = logging.getLogger("access")

    @app.middleware("http")
    async def _access_log(request: Request, call_next):
        # Set request_id into context as early as we can, from incoming header if present
        incoming_rid = request.headers.get("x-request-id")
        token = _request_id_ctx.set(incoming_rid)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            # Ensure contextvar is reset to avoid leaking into the next request
            _request_id_ctx.reset(token)

        duration_ms = int((time.perf_counter() - start) * 1000)

        # Prefer response header (set by main.py) to ensure final request_id matches what client sees
        req_id = response.headers.get("x-request-id") or incoming_rid or "-"

        # Re-set for this final log line (not strictly needed, but keeps consistency)
        _request_id_ctx.set(req_id)
        try:
            extra = {
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,  # path only (no query string)
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": _client_ip_from_scope(request.scope),
            }
            logger.info("request", extra=extra)
        finally:
            # Clean up context
            _request_id_ctx.set(None)

        return response


__all__ = [
    "setup_logging",
    "configure_uvicorn_logger_levels",
    "install_access_logger",
]
