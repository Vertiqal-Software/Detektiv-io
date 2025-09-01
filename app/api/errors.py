# app/api/errors.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("api.errors")

# Env knobs (optional)
_MAX_VALIDATION_ERRORS = int(os.getenv("ERRORS_MAX_VALIDATION_DETAILS", "50"))
_SCRUB_SECRETS = os.getenv("LOG_SCRUB_SECRETS", "1") == "1"
_NO_STORE_ERRORS = os.getenv("ERRORS_NO_STORE", "1") == "1"
_SHOW_500_EXCEPTION = os.getenv("ERRORS_SHOW_500_EXCEPTION", "0") == "1"  # dev aid only

_SECRET_KEYS = {"password", "token", "secret", "api_key", "authorization"}


def _cid(request: Request) -> str:
    """
    Correlation/request id used across logs and responses.
    Prefer inbound header; fall back to '-'.
    (Your middleware also sets x-request-id on responses.)
    """
    return request.headers.get("x-request-id") or "-"


def _sanitize_validation_errors(errs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reduce validation error payload to essentials and avoid leaking inputs/secrets.
    Keep fields: loc, msg, type. Truncate list to _MAX_VALIDATION_ERRORS.
    """
    cleaned: List[Dict[str, Any]] = []
    for e in errs[:_MAX_VALIDATION_ERRORS]:
        item: Dict[str, Any] = {
            "loc": e.get("loc"),
            "msg": e.get("msg"),
            "type": e.get("type"),
        }
        # Best-effort scrubbing for secret-y contexts
        if _SCRUB_SECRETS:
            loc = e.get("loc") or []
            if any(isinstance(p, str) and p.lower() in _SECRET_KEYS for p in loc):
                item["msg"] = "Invalid value"  # generic message
        cleaned.append(item)
    return cleaned


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Custom HTTPException handler.
    - Preserves your payload shape
    - Echoes x-request-id header
    - Adds path/method to help triage (kept out of payload to avoid breaking clients)
    - No-store to discourage caching of error responses (configurable)
    """
    cid = _cid(request)
    payload = {"error": {"code": exc.status_code, "message": exc.detail, "correlation_id": cid}}

    headers = {"x-request-id": cid}
    if _NO_STORE_ERRORS:
        headers["Cache-Control"] = "no-store"

    # Light debug log (no secrets)
    logger.info(
        "http_exception",
        extra={
            "request_id": cid,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
        },
    )

    return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom validation error handler.
    - Preserves your payload envelope and key names
    - Sanitizes details to avoid leaking inputs/secrets
    - Adds correlation id and no-store header
    """
    cid = _cid(request)
    details = _sanitize_validation_errors(exc.errors())

    payload = {
        "error": {
            "code": 422,
            "message": "Validation error",
            "details": details,
            "correlation_id": cid,
        }
    }

    headers = {"x-request-id": cid}
    if _NO_STORE_ERRORS:
        headers["Cache-Control"] = "no-store"

    logger.info(
        "validation_exception",
        extra={
            "request_id": cid,
            "path": request.url.path,
            "method": request.method,
            "status_code": 422,
            "details_count": len(details),
        },
    )

    return JSONResponse(status_code=422, content=payload, headers=headers)


# -------------------- NEW: generic 500 handler (non-breaking) --------------------

async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for unexpected exceptions. Keeps response minimal and consistent.
    - Returns: {"error": {"code": 500, "message": "Internal server error", "correlation_id": "<cid>"}}
    - In development (ERRORS_SHOW_500_EXCEPTION=1), adds "exception" class name to help debugging.
    """
    cid = _cid(request)

    # Avoid leaking secrets or stack traces to client; log server-side with correlation id.
    logger.exception(
        "unhandled_exception",
        extra={
            "request_id": cid,
            "path": request.url.path,
            "method": request.method,
            "status_code": 500,
        },
    )

    body: Dict[str, Any] = {
        "error": {"code": 500, "message": "Internal server error", "correlation_id": cid}
    }
    if _SHOW_500_EXCEPTION:
        body["error"]["exception"] = exc.__class__.__name__

    headers = {"x-request-id": cid}
    if _NO_STORE_ERRORS:
        headers["Cache-Control"] = "no-store"

    return JSONResponse(status_code=500, content=body, headers=headers)


# --- Installer -----------------------------------------------------------------

def install_error_handlers(app: FastAPI) -> None:
    """
    Register these handlers with a FastAPI app:
        from app.api.errors import install_error_handlers
        install_error_handlers(app)
    Safe to call multiple times.
    """
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)  # new

__all__ = [
    "install_error_handlers",
    "http_exception_handler",
    "validation_exception_handler",
    "unhandled_exception_handler",
]
