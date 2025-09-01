# app/api/auth.py
from __future__ import annotations

"""
Authentication API

Adds/strengthens:
- Optional rate limiting on /auth/login if a limiter is available
- Normalized email lookup before lockout checks
- WWW-Authenticate: Bearer headers on 401s
- Refresh flow accepts token from JSON body, HttpOnly cookie, or Authorization: Bearer header
- Safer fallbacks for get_db import
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Generator, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

# ---------- DB dependency ----------
# Prefer a shared API dependency if available; otherwise fallback to core session.
try:
    from app.api.deps import get_db  # type: ignore
except Exception:  # pragma: no cover
    try:
        from app.core.session import get_db  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("auth.py requires a get_db dependency") from e

# ---------- Optional rate limiter ----------
try:
    from app.core.rate_limit import limiter  # type: ignore
except Exception:  # pragma: no cover
    limiter = None  # type: ignore[assignment]

# ---------- Pydantic v1/v2 compatibility ----------
try:
    from pydantic import BaseModel, EmailStr, Field, ConfigDict  # v2
    _HAS_V2 = True
except Exception:  # pragma: no cover
    from pydantic import BaseModel, EmailStr, Field  # v1
    ConfigDict = None  # type: ignore
    _HAS_V2 = False

from app.models.user import User
from app.schemas.user import UserRead
from app.security.jwt_simple import (
    issue_token_pair,
    issue_access_token,
    decode_and_validate,
    JWTError,
    JWTExpired,
)
from app.security.deps import get_current_user  # DB-backed user with revocation checks
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Auth"])
log = logging.getLogger("api.auth")
bearer = HTTPBearer(auto_error=False)


# ---------- Env helpers ----------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name, "") or "").strip().lower()
    if v in {"1", "true", "yes", "y"}:
        return True
    if v in {"0", "false", "no", "n"}:
        return False
    return default


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Optional cookie helpers (non-breaking) ----------
ACCESS_TOKEN_COOKIE = os.getenv("ACCESS_TOKEN_COOKIE", "access_token")
REFRESH_TOKEN_COOKIE = os.getenv("REFRESH_TOKEN_COOKIE", "refresh_token")
AUTH_COOKIES = _env_bool("AUTH_COOKIES", False)
AUTH_COOKIE_SECURE = _env_bool("AUTH_COOKIE_SECURE", False)  # set True in prod behind HTTPS
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax")  # lax|strict|none
AUTH_COOKIE_DOMAIN = os.getenv("AUTH_COOKIE_DOMAIN", "")  # e.g., example.com
AUTH_COOKIE_PATH = os.getenv("AUTH_COOKIE_PATH", "/")
AUTH_COOKIE_MAX_AGE = _env_int("AUTH_COOKIE_MAX_AGE", 0)  # 0 => session cookie


def _set_cookie(
    response: Response,
    name: str,
    value: str,
    max_age: int = 0,
    http_only: bool = True,
) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age if max_age > 0 else None,
        expires=max_age if max_age > 0 else None,
        path=AUTH_COOKIE_PATH,
        domain=AUTH_COOKIE_DOMAIN if AUTH_COOKIE_DOMAIN else None,
        secure=AUTH_COOKIE_SECURE,
        httponly=http_only,
        samesite=AUTH_COOKIE_SAMESITE.lower(),  # "lax" | "strict" | "none"
    )


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        key=name,
        path=AUTH_COOKIE_PATH,
        domain=AUTH_COOKIE_DOMAIN if AUTH_COOKIE_DOMAIN else None,
    )


# ---------- Schemas ----------
class _OrmModel(BaseModel):
    if _HAS_V2:
        model_config = ConfigDict(from_attributes=True)  # type: ignore[attr-defined]
    else:  # pragma: no cover
        class Config:
            orm_mode = True


class LoginRequest(_OrmModel):
    email: EmailStr = Field(description="User email")
    password: str = Field(min_length=1, max_length=256, description="Plaintext password")


class TokenPairResponse(_OrmModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    access_expires_at: int  # epoch seconds
    refresh_expires_at: int  # epoch seconds


class RefreshRequest(_OrmModel):
    refresh_token: str = Field(min_length=1, description="Refresh token returned by /auth/login")


class AccessTokenResponse(_OrmModel):
    access_token: str
    token_type: str = "Bearer"
    access_expires_at: int  # epoch seconds


class LogoutResponse(_OrmModel):
    revoked: bool = True


# ---------- Internal helpers ----------
def _is_locked(user: User) -> bool:
    """Return True if the account is currently locked."""
    return bool(user.lockout_until and user.lockout_until > _now_utc())


def _register_failed_login(db: Session, user: User) -> None:
    """
    Increment failed_login_count and set lockout_until if threshold exceeded.
    Threshold and window are configurable via env:
      MAX_FAILED_LOGINS (default 5)
      LOCKOUT_MINUTES   (default 15)
    """
    max_attempts = _env_int("MAX_FAILED_LOGINS", 5)
    lock_minutes = _env_int("LOCKOUT_MINUTES", 15)

    user.failed_login_count = int(user.failed_login_count or 0) + 1
    if user.failed_login_count >= max_attempts:
        user.lockout_until = _now_utc() + timedelta(minutes=lock_minutes)
        log.warning("user_lockout email=%s until=%s", user.email, user.lockout_until)
        # Reset counter after lockout is applied
        user.failed_login_count = 0
    db.add(user)
    db.commit()


def _register_successful_login(db: Session, user: User) -> None:
    user.failed_login_count = 0
    user.last_login_at = _now_utc()
    db.add(user)
    db.commit()


def _unauth(detail: str) -> HTTPException:
    """Create a 401 with WWW-Authenticate header."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer_token(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if not credentials:
        return None
    if credentials.scheme.lower() != "bearer":
        return None
    token = (credentials.credentials or "").strip()
    return token or None


# ---------- Routes ----------
@router.post(
    "/login",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain access+refresh tokens",
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    response: Response = None,
) -> TokenPairResponse:
    """
    Authenticate with email/password. Enforces temporary lockouts on repeated failures.
    Returns a token pair with 'tv' (token_version) embedded for revocation support.

    If AUTH_COOKIES=1, also sets HttpOnly cookies:
      - ACCESS_TOKEN_COOKIE (default: access_token)
      - REFRESH_TOKEN_COOKIE (default: refresh_token)
    """
    if limiter is not None:  # optional rate limit
        # Apply a per-endpoint dynamic limit if configured in your limiter
        try:
            limiter.hit("auth_login")  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

    svc = UserService(db)

    # Normalize email before lookup to reduce mismatches
    email_norm = payload.email.strip().lower()
    user: Optional[User] = db.query(User).filter(User.email == email_norm).first()

    if user and _is_locked(user):
        # Deliberately use 429 (Too Many Requests) to indicate throttling/lockout
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account temporarily locked")

    # Authenticate (service handles hashing/verification)
    authed = svc.authenticate(email_norm, payload.password)
    if not authed:
        # If user exists, register a failed attempt (avoid user enumeration where possible)
        if user:
            try:
                _register_failed_login(db, user)
            except Exception:  # pragma: no cover
                log.exception("failed_login_update_error email=%s", email_norm)
        # Do not disclose which part failed
        raise _unauth("Invalid credentials")

    if not authed.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    # Success: reset counters, stamp last_login
    try:
        _register_successful_login(db, authed)
    except Exception:  # pragma: no cover
        log.exception("login_success_state_update_failed user_id=%s", authed.id)

    # Issue token pair carrying role, tenant, and token_version
    pair = issue_token_pair(
        user_id=authed.id,
        role=authed.role,
        tenant_id=authed.tenant_id,
        token_version=authed.token_version,
    )
    log.info("user_login_ok user_id=%s email=%s", authed.id, authed.email)

    # Optionally set HttpOnly cookies
    if AUTH_COOKIES and response is not None:
        access_ttl = _env_int("ACCESS_TOKEN_EXPIRES_SECONDS", 900)
        refresh_ttl = _env_int("REFRESH_TOKEN_EXPIRES_SECONDS", 14 * 24 * 3600)
        if AUTH_COOKIE_MAX_AGE > 0:
            _set_cookie(response, ACCESS_TOKEN_COOKIE, pair["access_token"], AUTH_COOKIE_MAX_AGE, http_only=True)
            _set_cookie(response, REFRESH_TOKEN_COOKIE, pair["refresh_token"], AUTH_COOKIE_MAX_AGE, http_only=True)
        else:
            _set_cookie(response, ACCESS_TOKEN_COOKIE, pair["access_token"], access_ttl, http_only=True)
            _set_cookie(response, REFRESH_TOKEN_COOKIE, pair["refresh_token"], refresh_ttl, http_only=True)

    return TokenPairResponse(
        access_token=pair["access_token"],
        refresh_token=pair["refresh_token"],
        token_type=pair["token_type"],
        access_expires_at=pair["access_expires_at"],
        refresh_expires_at=pair["refresh_expires_at"],
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token for a new access token",
)
def refresh(
    payload: Optional[RefreshRequest] = None,
    db: Session = Depends(get_db),
    response: Response = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    request: Request = None,
) -> AccessTokenResponse:
    """
    Validate the refresh token, then issue a new access token.
    Accepts token in JSON body, in the Authorization: Bearer header, or in an HttpOnly cookie
    (when AUTH_COOKIES=1). Body takes precedence if present.

    If AUTH_COOKIES=1, updates the access_token cookie.
    """
    raw_token: Optional[str] = None

    # Priority 1: JSON body
    if isinstance(payload, RefreshRequest) and payload.refresh_token:
        raw_token = payload.refresh_token.strip()

    # Priority 2: Cookie (if enabled)
    if not raw_token and AUTH_COOKIES and request is not None:
        cookie_token = (request.cookies.get(REFRESH_TOKEN_COOKIE) or "").strip()
        if cookie_token:
            raw_token = cookie_token

    # Priority 3: Authorization: Bearer <token>
    if not raw_token and credentials is not None:
        raw_token = _extract_bearer_token(credentials)

    if not raw_token:
        raise _unauth("Missing refresh token")

    try:
        claims = decode_and_validate(raw_token, expected_type="refresh")
    except JWTExpired:
        raise _unauth("Refresh token expired")
    except JWTError:
        raise _unauth("Invalid refresh token")

    sub = claims.get("sub")
    if not sub:
        raise _unauth("Invalid token (sub)")

    try:
        user_id = int(sub)
    except Exception:
        raise _unauth("Invalid token (subject)")

    user: Optional[User] = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise _unauth("User not found or inactive")

    # Token revocation: 'tv' (token_version) in token must match current DB value
    tv = claims.get("tv")
    if tv is None or int(tv) != int(user.token_version):
        raise _unauth("Token revoked")

    # Optional tenant consistency check
    tid_claim = claims.get("tid")
    if (tid_claim is not None) and (user.tenant_id is not None) and (int(tid_claim) != int(user.tenant_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    # Issue fresh access token
    token = issue_access_token(
        user_id=user.id,
        role=user.role,
        tenant_id=user.tenant_id,
        token_version=user.token_version,
    )
    # Recompute expiry epoch (mirror jwt_simple defaults)
    access_ttl = _env_int("ACCESS_TOKEN_EXPIRES_SECONDS", 900)
    access_expires_at = int((_now_utc() + timedelta(seconds=access_ttl)).timestamp())

    # Optionally set/refresh the access cookie
    if AUTH_COOKIES and response is not None:
        if AUTH_COOKIE_MAX_AGE > 0:
            _set_cookie(response, ACCESS_TOKEN_COOKIE, token, AUTH_COOKIE_MAX_AGE, http_only=True)
        else:
            _set_cookie(response, ACCESS_TOKEN_COOKIE, token, access_ttl, http_only=True)

    log.info("token_refreshed user_id=%s", user.id)
    return AccessTokenResponse(access_token=token, access_expires_at=access_expires_at)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout (revokes tokens by bumping token_version)",
)
def logout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    response: Response = None,
) -> LogoutResponse:
    """
    Invalidate all existing tokens by incrementing token_version.
    Clients must discard stored tokens; subsequent use will fail with 'Token revoked'.

    If AUTH_COOKIES=1, clears the auth cookies.
    """
    user.token_version = int(user.token_version or 0) + 1
    db.add(user)
    db.commit()
    log.info("user_logout_revoked user_id=%s", user.id)

    if AUTH_COOKIES and response is not None:
        _clear_cookie(response, ACCESS_TOKEN_COOKIE)
        _clear_cookie(response, REFRESH_TOKEN_COOKIE)

    return LogoutResponse(revoked=True)


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Return the current user's profile",
)
def me(user: User = Depends(get_current_user)) -> UserRead:
    """Return the authenticated user's profile."""
    return UserRead.model_validate(user) if _HAS_V2 else UserRead.from_orm(user)  # type: ignore[attr-defined]
