# app/api/deps.py
from __future__ import annotations

import os
import logging
from typing import Optional, Tuple, Generator

from fastapi import Depends, Query, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# -------------------------------------------------------------------------
# Shared DB + auth imports (kept lightweight; no side effects)
# -------------------------------------------------------------------------
from app.core.session import SessionLocal
from app.models.user import User

# Replace legacy JWT import with jwt_simple (non-breaking)
from app.security.jwt_simple import decode_and_validate, JWTError, JWTExpired

# Logger for this module
_log = logging.getLogger("api.deps")

# -----------------------------------------------------------------------------
# Env-tunable defaults for pagination (evaluated at import time)
# -----------------------------------------------------------------------------
_API_DEFAULT_PAGE_SIZE = max(1, int(os.getenv("API_DEFAULT_PAGE_SIZE", "50")))
_API_MAX_PAGE_SIZE = max(_API_DEFAULT_PAGE_SIZE, int(os.getenv("API_MAX_PAGE_SIZE", "1000")))

# Keep existing functions EXACTLY as-is (do not modify) -----------------------

def pagination(
    limit: int = Query(50, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip for paging"),
) -> Tuple[int, int]:
    return limit, offset

def request_id(x_request_id: Optional[str] = Header(None)) -> str:
    """
    Returns the inbound request id header (if any).
    Your middleware generates one if missing, but this allows handlers to read it.
    """
    return x_request_id or "-"

# -----------------------------------------------------------------------------
# ADDITIVE HELPERS (optional to use)
# -----------------------------------------------------------------------------

def pagination_env(
    limit: int = Query(
        _API_DEFAULT_PAGE_SIZE,
        ge=1,
        le=_API_MAX_PAGE_SIZE,
        description=f"Max rows to return (default {_API_DEFAULT_PAGE_SIZE}, max {_API_MAX_PAGE_SIZE})",
    ),
    offset: int = Query(0, ge=0, description="Rows to skip for paging"),
) -> Tuple[int, int]:
    """
    Pagination helper whose defaults and max are driven by environment variables:
      - API_DEFAULT_PAGE_SIZE (default 50)
      - API_MAX_PAGE_SIZE (default 1000)
    """
    return limit, offset


def pagination_ordered(
    limit_offset: Tuple[int, int] = Depends(pagination_env),
    order: Optional[str] = Query(
        "desc",
        description="Sort order; one of: asc, desc",
    ),
) -> Tuple[int, int, str]:
    """
    Pagination + order helper. Validates order and normalizes to lowercase.
    """
    limit, offset = limit_offset
    ord_norm = (order or "desc").lower()
    if ord_norm not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'")
    return limit, offset, ord_norm


def tenant_dep(x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id")) -> str:
    """
    Resolve tenant from header; falls back to 'public' if missing/blank.
    """
    tenant = (x_tenant_id or "").strip()
    return tenant or "public"


def get_tenant_id(tenant: str = Depends(tenant_dep)) -> str:
    """
    Convenience wrapper so handlers can `Depends(get_tenant_id)` directly.
    """
    return tenant


def normalized_query(
    q: Optional[str] = Query(None, description="Free-text query (trimmed)"),
    require_non_empty: bool = False,
) -> Optional[str]:
    """
    Trims incoming query strings.
    If require_non_empty=True and the trimmed value is empty -> 422.
    """
    if q is None:
        if require_non_empty:
            raise HTTPException(status_code=422, detail="q must not be empty")
        return None
    q_clean = q.strip()
    if require_non_empty and not q_clean:
        raise HTTPException(status_code=422, detail="q must not be empty")
    return q_clean or None


# -----------------------------------------------------------------------------
# Database session dependency (shared)
# -----------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """
    Shared DB session dependency using the canonical engine/session.
    Ensures proper close after request handling.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception as e:
            _log.debug("Session close error: %s", e)


# -----------------------------------------------------------------------------
# Auth dependencies (Bearer JWT)
# -----------------------------------------------------------------------------
_security = HTTPBearer(auto_error=False)

def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )

def _forbidden(detail: str = "Insufficient privileges") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate Authorization: Bearer <token>, verify signature/exp,
    load the user from DB, ensure user is active, and return the User ORM object.

    Non-breaking improvements:
    - Uses jwt_simple.decode_and_validate(expected_type='access')
    - Checks token_version ('tv') and optional tenant consistency ('tid')
    """
    if not credentials:
        raise _unauthorized()

    scheme = (credentials.scheme or "").lower().strip()
    if scheme != "bearer":
        raise _unauthorized("Invalid auth scheme")

    token = credentials.credentials
    try:
        claims = decode_and_validate(token, expected_type="access")
        sub = claims.get("sub")
        if sub is None:
            raise ValueError("missing sub")
        user_id = int(sub)
    except JWTExpired:
        raise _unauthorized("Token expired")
    except (JWTError, ValueError) as e:
        _log.warning("token_verify_failed: %s", e)
        raise _unauthorized("Invalid token")

    try:
        user = db.get(User, user_id)
    except SQLAlchemyError as e:
        _log.error("db_lookup_failed user_id=%s err=%s", user_id, e)
        # Do not leak DB details to client
        raise _unauthorized("Invalid token")

    if not user:
        # Do not reveal whether a user exists
        raise _unauthorized("Invalid token")
    if not user.is_active:
        raise _forbidden("Inactive user")

    # Token revocation: tv (token_version) must match
    tv = claims.get("tv")
    if tv is None or int(tv) != int(getattr(user, "token_version", 0)):
        raise _unauthorized("Token revoked")

    # Optional tenant consistency if both sides carry a tenant
    tid = claims.get("tid")
    if tid is not None and getattr(user, "tenant_id", None) is not None:
        if int(tid) != int(user.tenant_id):  # type: ignore[arg-type]
            raise _forbidden("Tenant mismatch")

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Optional variant: returns None if no/invalid token.
    Handy for endpoints that work for both anonymous and logged-in users.
    """
    try:
        return await get_current_user(credentials, db)  # type: ignore[arg-type]
    except HTTPException:
        return None


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """
    Ensure the current user has superuser privileges.
    Returns the User if allowed; raises 403 otherwise.
    """
    if not bool(getattr(current_user, "is_superuser", False)):
        raise _forbidden("Admin privileges required")
    return current_user


__all__ = [
    # original exports
    "pagination",
    "request_id",
    "pagination_env",
    "pagination_ordered",
    "tenant_dep",
    "get_tenant_id",
    "normalized_query",
    # db + auth
    "get_db",
    "get_current_user",
    "get_current_user_optional",
    "require_superuser",
]
