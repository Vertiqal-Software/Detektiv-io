# app/security/deps.py
from __future__ import annotations

from typing import Any, Dict, Optional, Callable, Set, List
import logging
import os

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models.user import User

# Prefer session provider from app.core.session; fall back to app.core.database if needed.
try:
    from app.core.session import get_db  # type: ignore
except Exception:  # pragma: no cover
    from app.core.database import get_db  # type: ignore

from app.security.jwt_simple import (
    decode_and_validate,
    JWTError,
    JWTExpired,
    JWTInvalidSignature,
    JWTInvalidType,
    JWTInvalidAudience,
    JWTInvalidIssuer,
)

logger = logging.getLogger(__name__)

# HTTP Bearer scheme for reading Authorization header; we allow missing header (auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Default allowed roles; can be overridden via env var ALLOWED_ROLES="admin,analyst,..."
ALLOWED_ROLES: Set[str] = {"admin", "analyst"}
try:
    _roles_env = os.getenv("ALLOWED_ROLES", "")
    if _roles_env.strip():
        env_roles = {r.strip() for r in _roles_env.split(",") if r.strip()}
        if env_roles:
            ALLOWED_ROLES = env_roles
            logger.info("ALLOWED_ROLES overridden via env: %s", sorted(ALLOWED_ROLES))
except Exception:  # pragma: no cover - defensive
    pass

# Optional cookie name fallback for bearer token; disabled by default unless cookie present
ACCESS_TOKEN_COOKIE = os.getenv("ACCESS_TOKEN_COOKIE", "access_token")

# Allow anonymous user in DEBUG if explicitly enabled (used by *_optional deps)
ALLOW_ANONYMOUS_IN_DEBUG = os.getenv("ALLOW_ANONYMOUS_IN_DEBUG", "0").lower() in {"1", "true", "yes", "y"}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _extract_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    """
    Extract and validate the token from an Authorization header of type Bearer.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = credentials.credentials or ""
    if not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
        )
    return token


def _fallback_token_from_cookie_or_query(request: Request) -> Optional[str]:
    """
    Optional token fallback:
      - read from cookie named ACCESS_TOKEN_COOKIE (default: "access_token")
      - or from query params: ?access_token=... / ?token=...
    Only used by the *_optional dependencies; does not affect strict auth.
    """
    if not request:
        return None
    try:
        # 1) Cookie
        if ACCESS_TOKEN_COOKIE in request.cookies:
            raw = (request.cookies.get(ACCESS_TOKEN_COOKIE) or "").strip()
            if raw.startswith("Bearer "):
                raw = raw[7:].strip()
            if raw:
                return raw
        # 2) Query param
        for key in ("access_token", "token"):
            if key in request.query_params:
                raw = (request.query_params.get(key) or "").strip()
                if raw.startswith("Bearer "):
                    raw = raw[7:].strip()
                if raw:
                    return raw
    except Exception:  # pragma: no cover
        pass
    return None


def _fetch_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


# -----------------------------------------------------------------------------
# Claims / User dependencies (strict)
# -----------------------------------------------------------------------------

def get_current_claims(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Dict[str, Any]:
    """
    Validate an **access** token and return its claims.

    Enforces:
      - Signature, exp/nbf (with leeway from env), optional iss/aud from env
      - Token type must be 'access'
      - Presence of 'sub'
    """
    token = _extract_bearer_token(credentials)
    try:
        claims = decode_and_validate(token, expected_type="access")
    except JWTExpired as e:
        logger.info("Access token expired: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except (JWTInvalidSignature, JWTInvalidType, JWTInvalidAudience, JWTInvalidIssuer) as e:
        logger.warning("Invalid access token: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as e:
        logger.warning("Token validation error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Unexpected token processing error")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload (sub)")

    # Optional sanity checks on role/tenant
    role = claims.get("role")
    if role is not None and role not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload (role)")

    return claims


def get_current_user(
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(get_current_claims),
    request: Request = None,
) -> User:
    """
    Load the current user from DB and enforce:
      - user exists
      - user is active
      - token_version matches (revocation support)
      - optional tenant consistency check (if both sides have tenant IDs)
    """
    # Serve from per-request cache if available
    if request is not None and hasattr(request, "state"):
        cached = getattr(request.state, "user", None)
        if isinstance(cached, User):
            return cached

    # 'sub' comes from get_current_claims; it is required there.
    sub = claims["sub"]
    try:
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")

    user: Optional[User] = _fetch_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    # Token revocation: compare tv (token_version) claim with DB value
    tv_claim = claims.get("tv")
    if tv_claim is None or int(tv_claim) != int(user.token_version):
        # Treat as revoked; caller should re-authenticate
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    # Tenant consistency hook: if both claim and user carry tenant IDs, ensure match
    tid_claim = claims.get("tid")
    if (tid_claim is not None) and (user.tenant_id is not None) and (int(tid_claim) != int(user.tenant_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    # Cache on request to avoid duplicate DB hits in same request
    if request is not None and hasattr(request, "state"):
        try:
            setattr(request.state, "user", user)
        except Exception:
            pass

    return user


# -----------------------------------------------------------------------------
# Role-based guards (strict)
# -----------------------------------------------------------------------------

def require_roles(*roles: str) -> Callable[[User], User]:
    """
    Dependency factory: ensure the current user has one of the required roles.

    Example:
        @router.get("/admin")
        def admin_view(user: User = Depends(require_roles("admin"))):
            ...
    """
    required = set(roles)
    invalid = required - ALLOWED_ROLES
    if invalid:
        raise RuntimeError(f"Unknown roles specified: {sorted(invalid)}")

    def _dep(user: User = Depends(get_current_user)) -> User:
        # Superusers short-circuit
        if getattr(user, "is_superuser", False):
            return user
        if getattr(user, "role", None) not in required:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _dep


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Shortcut for admin-only routes (or superuser)."""
    if getattr(user, "is_superuser", False) or getattr(user, "role", None) == "admin":
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")


# -----------------------------------------------------------------------------
# Backwards-compatibility and optional helpers
# -----------------------------------------------------------------------------

# Backwards compatibility shim:
# Some handlers might already depend on `require_user` returning claims.
# Keep a thin wrapper but prefer using get_current_user() going forward.
def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Dict[str, Any]:
    """
    Deprecated: returns claims only. Prefer get_current_user() for DB-backed checks.
    """
    return get_current_claims(credentials)  # type: ignore[return-value]


def get_current_claims_optional(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Optional[Dict[str, Any]]:
    """
    Optional variant:
      - If Authorization header with Bearer token exists, validate and return claims.
      - Else try cookie/query fallback.
      - If still no token, return None (or raise 401 if not in debug mode and anonymous not allowed).
    """
    token: Optional[str] = None

    # Header path (preferred)
    if credentials and getattr(credentials, "scheme", "").lower() == "bearer":
        token = (credentials.credentials or "").strip()

    # Fallbacks (cookie / query)
    if not token:
        token = _fallback_token_from_cookie_or_query(request)

    if not token:
        # No token available
        if ALLOW_ANONYMOUS_IN_DEBUG and os.getenv("DEBUG", "false").lower() == "true":
            return None
        return None  # For optional dep, just return None

    # Validate
    try:
        claims = decode_and_validate(token, expected_type="access")
    except JWTExpired as e:
        logger.info("Access token expired (optional): %s", e)
        return None
    except (JWTInvalidSignature, JWTInvalidType, JWTInvalidAudience, JWTInvalidIssuer, JWTError) as e:
        logger.debug("Invalid access token (optional): %s", e)
        return None
    except Exception as e:  # pragma: no cover
        logger.debug("Unexpected token processing error (optional): %s", e)
        return None

    # Minimal payload sanity
    if "sub" not in claims:
        return None
    role = claims.get("role")
    if role is not None and role not in ALLOWED_ROLES:
        return None

    return claims


def get_current_user_optional(
    db: Session = Depends(get_db),
    claims: Optional[Dict[str, Any]] = Depends(get_current_claims_optional),
    request: Request = None,
) -> Optional[User]:
    """
    Optional user dependency:
      - Returns User if token is present and valid.
      - Returns None when no/invalid token.
      - In DEBUG with ALLOW_ANONYMOUS_IN_DEBUG=1, allows None for anonymous access.
    """
    if not claims:
        if ALLOW_ANONYMOUS_IN_DEBUG and os.getenv("DEBUG", "false").lower() == "true":
            return None
        return None

    # As in get_current_user but tolerant (returns None on failure)
    sub = claims.get("sub")
    try:
        user_id = int(sub)  # type: ignore[arg-type]
    except Exception:
        return None

    user = _fetch_user_by_id(db, user_id)
    if not user or not getattr(user, "is_active", False):
        return None

    # Token revocation check
    tv_claim = claims.get("tv")
    if tv_claim is None or int(tv_claim) != int(getattr(user, "token_version", 0)):
        return None

    # Tenant match if both present
    tid_claim = claims.get("tid")
    user_tid = getattr(user, "tenant_id", None)
    if (tid_claim is not None) and (user_tid is not None) and (int(tid_claim) != int(user_tid)):
        return None

    if request is not None and hasattr(request, "state"):
        try:
            setattr(request.state, "user", user)
        except Exception:
            pass

    return user


# -----------------------------------------------------------------------------
# Scope & tenant helpers (additive)
# -----------------------------------------------------------------------------

def require_scopes(*scopes: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Dependency factory to ensure the token includes all given scopes.

    The token may carry scopes either as:
      - list in 'scp', or
      - space/comma-separated string in 'scope' or 'scp'

    Example:
        @router.get("/reports")
        def reports(claims = Depends(require_scopes("reports:read"))):
            ...
    """
    required = {s.strip() for s in scopes if s and s.strip()}
    if not required:
        raise RuntimeError("require_scopes requires at least one scope")

    def _dep(claims: Dict[str, Any] = Depends(get_current_claims)) -> Dict[str, Any]:
        token_scopes: Set[str] = set()
        raw = claims.get("scp", claims.get("scope"))
        if isinstance(raw, list):
            token_scopes = {str(s).strip() for s in raw if str(s).strip()}
        elif isinstance(raw, str):
            token_scopes = {s.strip() for s in raw.replace(",", " ").split() if s.strip()}
        if not required.issubset(token_scopes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient scope")
        return claims

    return _dep


def require_tenant() -> Callable[[Dict[str, Any], int], Dict[str, Any]]:
    """
    Dependency factory that enforces the 'tid' claim matches a route tenant_id parameter.

    Example:
        @router.get("/tenants/{tenant_id}/companies")
        def list_companies(
            claims = Depends(require_tenant()),
        ):
            ...
    """
    def _dep(tenant_id: int, claims: Dict[str, Any] = Depends(get_current_claims)) -> Dict[str, Any]:
        tid = claims.get("tid")
        if tid is None or int(tid) != int(tenant_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
        return claims

    return _dep


# -----------------------------------------------------------------------------
# Admin bootstrap (dev)
# -----------------------------------------------------------------------------

def admin_credentials() -> Dict[str, str]:
    """
    Development-only: returns admin username/password from environment.
    DO NOT use in production; keep for local bootstrap flows.

    Set:
      ADMIN_USERNAME=admin
      ADMIN_PASSWORD=... (must be set or a 500 is raised)
    """
    user = os.getenv("ADMIN_USERNAME", "admin")
    pwd = os.getenv("ADMIN_PASSWORD")
    if not pwd:
        # Force explicit password set to avoid accidental open admin.
        raise HTTPException(
            status_code=500,
            detail="Server not configured: ADMIN_PASSWORD unset",
        )
    return {"username": user, "password": pwd}

