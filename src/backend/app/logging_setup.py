# app/logging_setup.py
from __future__ import annotations

import json
import logging
import os
import re
import time
import contextvars
import uuid
import random
from typing import Any, Dict, Optional, Iterable
from contextlib import contextmanager

from fastapi import FastAPI, Request, Response

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
        msg = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-=/]+", "Bearer ***", msg)

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

        # Generic very-long-hex/base64-ish blobs (likely tokens) -> ***
        msg = re.sub(r"(?i)\b([A-F0-9]{24,}|[A-Za-z0-9_\-]{32,})\b", "***", msg)

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
            "route_name",
            "trace_id",
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
        route = getattr(record, "route_name", None)
        route_part = f" route={route}" if route else ""
        return f"[{ts}] {record.levelname:<7} {record.name} rid={rid}{route_part} :: {msg}"


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


# ---------------------------- EXTRA SANITIZER (NEW) ---------------------------- #
# Some code paths may log with `extra={"name": ...}` or other keys that collide
# with standard LogRecord attributes (e.g. name, msg, levelname, etc.), causing:
#   KeyError: "Attempt to overwrite 'name' in LogRecord"
# We globally sanitize `extra` in Logger._log to prevent crashes (add-only).
_LOG_EXTRA_SANITIZER_INSTALLED = False
_RESERVED_LOGRECORD_ATTRS: Optional[set[str]] = None


def _reserved_logrecord_attrs() -> set[str]:
    global _RESERVED_LOGRECORD_ATTRS
    if _RESERVED_LOGRECORD_ATTRS is None:
        # Create a dummy record to discover standard attributes dynamically
        rec = logging.LogRecord("x", logging.INFO, __file__, 1, "m", (), None)
        _RESERVED_LOGRECORD_ATTRS = set(vars(rec).keys())
    return _RESERVED_LOGRECORD_ATTRS


def _sanitize_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of `extra` safe for logging.makeRecord(): any key that would
    collide with a LogRecord attribute is prefixed with 'extra_'.
    """
    try:
        reserved = _reserved_logrecord_attrs()
    except Exception:
        # Fallback to a conservative, well-known set
        reserved = {
            "name", "msg", "args", "levelname", "levelno",
            "pathname", "filename", "module", "exc_info", "exc_text",
            "stack_info", "lineno", "funcName", "created", "msecs",
            "relativeCreated", "thread", "threadName", "processName", "process",
        }
    safe: Dict[str, Any] = {}
    for k, v in (extra or {}).items():
        key = str(k)
        if key in reserved:
            key = f"extra_{key}"
        safe[key] = v
    return safe


def _install_global_extra_sanitizer() -> None:
    """
    Monkey-patch logging.Logger._log once per process to sanitize `extra`.
    This is intentionally minimal and safe; if sanitizer fails we fall back
    to the original behavior rather than blocking logging.
    """
    global _LOG_EXTRA_SANITIZER_INSTALLED
    if _LOG_EXTRA_SANITIZER_INSTALLED:
        return

    original_log = logging.Logger._log

    def _log_with_sanitized_extra(self, level, msg, args,
                                  exc_info=None, extra=None,
                                  stack_info=False, stacklevel=1):
        if isinstance(extra, dict):
            try:
                extra = _sanitize_extra(extra)
            except Exception:
                # Never block logging if sanitizer fails
                pass
        return original_log(self, level, msg, args, exc_info, extra, stack_info, stacklevel)

    logging.Logger._log = _log_with_sanitized_extra  # type: ignore[method-assign]
    _LOG_EXTRA_SANITIZER_INSTALLED = True
# ---------------------------------------------------------------------------- #


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

    # NEW: install global extra sanitizer to prevent KeyError on reserved keys
    _install_global_extra_sanitizer()

    setattr(setup_logging, "_configured", True)  # type: ignore[attr-defined]


def configure_uvicorn_logger_levels(app_level: Optional[str] = None) -> None:
    """
    Optional helper if you want to align uvicorn.* logger level with your app.
    Use like: configure_uvicorn_logger_levels(logging.getLogger().level)
    """
    level = app_level or logging.getLogger().level
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel("WARNING")


def _first_nonempty(*values: Optional[str]) -> Optional[str]:
    for v in values:
        if v:
            vs = v.strip()
            if vs:
                return vs
    return None


def _parse_csv_env(name: str, default: str = "") -> Iterable[str]:
    raw = os.getenv(name, default)
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _client_ip_from_scope(scope: Dict[str, Any]) -> str:
    """
    Determine client IP with common proxy headers:
      - X-Forwarded-For: take first value
      - X-Real-IP
      - CF-Connecting-IP
    Fallback to ASGI scope client tuple.
    """
    try:
        headers_list = scope.get("headers", [])
        headers: Dict[str, str] = {}
        for k, v in headers_list:
            try:
                headers[k.decode("latin-1").lower()] = v.decode("latin-1")
            except Exception:
                # Fallback decode
                headers[k.decode(errors="ignore").lower()] = v.decode(errors="ignore")

        # Allow header preference via env
        header_order = tuple(h.lower() for h in _parse_csv_env(
            "LOG_CLIENT_IP_HEADERS", "x-forwarded-for,x-real-ip,cf-connecting-ip"
        ))

        for hdr in header_order:
            val = headers.get(hdr)
            if not val:
                continue
            if hdr == "x-forwarded-for":
                # First IP in the list is the original client
                ip = val.split(",")[0].strip()
                if ip:
                    return ip
            else:
                v = val.strip()
                if v:
                    return v

        client = scope.get("client")
        if isinstance(client, (list, tuple)) and client:
            return str(client[0]) or "unknown"
        return "unknown"
    except Exception:
        return "unknown"


def _trace_id_from_headers(headers: Dict[str, str]) -> Optional[str]:
    """
    Extract W3C trace id from 'traceparent' header if present (format: 00-<traceId>-<spanId>-flags).
    """
    try:
        tp = headers.get("traceparent")
        if not tp:
            return None
        parts = tp.split("-")
        if len(parts) >= 3 and len(parts[1]) == 32:
            return parts[1]
        return None
    except Exception:
        return None


def install_access_logger(app: FastAPI) -> None:
    """
    Add a middleware that emits JSON (or pretty) access logs with:
      method, path, status_code, duration_ms, request_id, client_ip.
    Does NOT log query strings or headers to avoid leaking secrets.
    Also sets a contextvar so downstream logs include request_id automatically.

    Idempotent: calling this multiple times will not add duplicate middleware.

    Env:
      - LOG_ACCESS_ENABLED=1/0 (default 1): master switch
      - LOG_EXCLUDE_PATHS="/health,/metrics,/readiness,/health/db" (CSV)
      - LOG_REQUEST_ID_HEADER="x-request-id"
      - LOG_SAMPLE_RATE=1.0 (0.0..1.0): probabilistic sampling of access logs
      - LOG_ACCESS_TRACEPARENT=1/0 (default 1): include trace_id if 'traceparent' header present
      - LOG_ACCESS_LOG_QUERY=0/1 (default 0): if 1, log '?query' into 'query' field
    """
    # Prevent double-install when reloads or duplicate imports occur
    if getattr(app.state, "access_logger_installed", False):
        return
    setattr(app.state, "access_logger_installed", True)

    access_enabled = os.getenv("LOG_ACCESS_ENABLED", "1") == "1"
    rid_header = os.getenv("LOG_REQUEST_ID_HEADER", "x-request-id").lower()
    exclude_paths = tuple(_parse_csv_env(
        "LOG_EXCLUDE_PATHS", "/health,/metrics,/readiness,/health/db"
    ))
    try:
        sample_rate = float(os.getenv("LOG_SAMPLE_RATE", "1.0"))
    except Exception:
        sample_rate = 1.0
    sample_rate = max(0.0, min(sample_rate, 1.0))

    include_traceparent = os.getenv("LOG_ACCESS_TRACEPARENT", "1") == "1"
    log_query = os.getenv("LOG_ACCESS_LOG_QUERY", "0") == "1"

    logger = logging.getLogger("access")

    @app.middleware("http")
    async def _access_log(request: Request, call_next):
        # Set request_id into context as early as we can, from incoming header if present
        incoming_rid = request.headers.get(rid_header)
        # Generate one if missing or blank
        req_id_to_set = _first_nonempty(incoming_rid, uuid.uuid4().hex)
        token = _request_id_ctx.set(req_id_to_set)

        # Extract route name (if already resolved) and trace id
        route_name = None
        try:
            route = request.scope.get("route")
            if route is not None:
                route_name = getattr(route, "name", None)
        except Exception:
            route_name = None

        # Build lowercase headers dict for traceparent parsing
        try:
            hdrs_lower = {k.lower(): v for k, v in request.headers.items()}
        except Exception:
            hdrs_lower = {}

        trace_id = _trace_id_from_headers(hdrs_lower) if include_traceparent else None

        start = time.perf_counter()
        response: Optional[Response] = None
        status_code_for_log = 500  # assume failure until we succeed
        try:
            response = await call_next(request)
            status_code_for_log = getattr(response, "status_code", 200)
        except Exception:
            # Even if downstream raises, we still want to log; re-raise after logging
            status_code_for_log = 500
            raise
        finally:
            # Ensure contextvar is reset to avoid leaking into the next request
            _request_id_ctx.reset(token)

        duration_ms = int((time.perf_counter() - start) * 1000)

        # Prefer response header to ensure final request_id matches what client sees
        final_req_id = None
        if response is not None:
            # Ensure the request id header is present on the response
            final_req_id = response.headers.get(rid_header)
            if not final_req_id:
                final_req_id = req_id_to_set or uuid.uuid4().hex
                response.headers[rid_header] = final_req_id

        final_req_id = final_req_id or req_id_to_set or "-"

        # Path only (no query), with optional query logging
        path = request.url.path
        query_str = str(request.url.query) if log_query else None

        # Skip logging for noisy health/metrics endpoints if configured
        should_exclude = any(path.startswith(p) for p in exclude_paths)

        # Apply sampling (but never sample out error responses)
        sampled_out = (random.random() > sample_rate) and (status_code_for_log < 500)

        if access_enabled and (not should_exclude) and (not sampled_out):
            # Re-set for this final log line (not strictly needed, but keeps consistency)
            _request_id_ctx.set(final_req_id)
            try:
                extra = {
                    "request_id": final_req_id,
                    "method": request.method,
                    "path": path,
                    "status_code": status_code_for_log,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip_from_scope(request.scope),
                    "route_name": route_name,
                }
                if trace_id:
                    extra["trace_id"] = trace_id
                if query_str:
                    extra["query"] = query_str
                logger.info("request", extra=extra)
            finally:
                # Clean up context
                _request_id_ctx.set(None)

        return response


# --------- small helpers for background jobs / manual logging --------- #

def get_request_id(default: Optional[str] = None) -> Optional[str]:
    """
    Read the current request_id from context (if any).
    Useful in background tasks spawned from requests to correlate logs.
    """
    rid = _request_id_ctx.get()
    return rid if rid is not None else default


def set_request_id(value: Optional[str]) -> None:
    """
    Imperative setter; prefer the context manager 'request_context' when possible.
    """
    _request_id_ctx.set(value)


@contextmanager
def request_context(request_id: Optional[str]):
    """
    Context manager to bind a request_id for the duration of a block.
    Example:
        with request_context(existing_rid):
            logger.info("processing batch")
    """
    token = _request_id_ctx.set(request_id)
    try:
        yield
    finally:
        _request_id_ctx.reset(token)


__all__ = [
    "setup_logging",
    "configure_uvicorn_logger_levels",
    "install_access_logger",
    "get_request_id",
    "set_request_id",
    "request_context",
]
