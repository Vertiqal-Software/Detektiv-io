# app/security/jwt_simple.py
"""
JWT utilities (HS256) with access/refresh/password-reset tokens, token versioning, and strict validation.

Environment variables:
- JWT_SECRET (preferred) OR SECRET_KEY (fallback)              : HMAC secret (base64 or raw string)
- JWT_SECRET_FILE / SECRET_KEY_FILE (optional)                 : path to file containing the secret
- JWT_ISSUER (optional)                                       : 'iss' claim to include & validate
- JWT_AUDIENCE (optional)                                     : 'aud' claim to include & validate
- ACCESS_TOKEN_EXPIRES_SECONDS (optional)                     : default 900 (15 minutes)
- REFRESH_TOKEN_EXPIRES_SECONDS (optional)                    : default 1209600 (14 days)
- PASSWORD_RESET_EXPIRES_SECONDS (optional)                   : default 900 (15 minutes)
- JWT_LEEWAY_SECONDS (optional)                               : default 30 (clock skew leeway)

Additional compatibility knobs (non-breaking additions):
- ACCESS_TOKEN_EXPIRE_MINUTES (optional)                      : used if *_EXPIRES_SECONDS not set
- REFRESH_TOKEN_EXPIRE_DAYS (optional)                        : used if *_EXPIRES_SECONDS not set

Security notes:
- In production, set a strong, stable secret (JWT_SECRET or SECRET_KEY). This module can
  fall back to a random secret per process for development only; tokens will be invalid
  after restart.
- Token revocation: callers must compare payload['tv'] to the user's current token_version.
  If they differ, treat the token as revoked.
"""
from __future__ import annotations

import base64
import os
import json
import time
import hmac
import hashlib
from typing import Any, Dict, Optional, Tuple

# ---------------- Errors ----------------
class JWTError(Exception):
    """Generic JWT validation error."""


class JWTExpired(JWTError):
    """Token has expired."""


class JWTNotYetValid(JWTError):
    """Token not yet valid (nbf)."""


class JWTInvalidSignature(JWTError):
    """Signature check failed."""


class JWTInvalidType(JWTError):
    """Token type mismatch (expected access/refresh/pwreset)."""


class JWTInvalidIssuer(JWTError):
    """Issuer mismatch."""


class JWTInvalidAudience(JWTError):
    """Audience mismatch."""


class JWTInvalidHeader(JWTError):
    """Invalid or unsupported header (e.g., alg)."""


# ---------------- Internal helpers ----------------
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _json_dumps(obj: Any) -> bytes:
    # sort_keys makes signatures deterministic
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(msg: bytes, secret: bytes) -> str:
    return _b64url_encode(hmac.new(secret, msg, hashlib.sha256).digest())


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except Exception:
        return default


def _env_from_minutes_or_seconds(
    seconds_name: str,
    default_seconds: int,
    minutes_name: Optional[str] = None,
) -> int:
    """
    Return seconds, first honoring the explicit *seconds* env.
    If unset, honor an alternate '*_MINUTES' env (converted to seconds), otherwise default.
    """
    v = os.getenv(seconds_name)
    if v and v.strip():
        try:
            return int(v)
        except Exception:
            pass
    if minutes_name:
        vm = os.getenv(minutes_name)
        if vm and vm.strip():
            try:
                return int(float(vm) * 60.0)
            except Exception:
                pass
    return default_seconds


def _env_from_days_or_seconds(
    seconds_name: str,
    default_seconds: int,
    days_name: Optional[str] = None,
) -> int:
    """
    Return seconds, first honoring the explicit *seconds* env.
    If unset, honor an alternate '*_DAYS' env (converted to seconds), otherwise default.
    """
    v = os.getenv(seconds_name)
    if v and v.strip():
        try:
            return int(v)
        except Exception:
            pass
    if days_name:
        vd = os.getenv(days_name)
        if vd and vd.strip():
            try:
                return int(float(vd) * 24.0 * 3600.0)
            except Exception:
                pass
    return default_seconds


def _read_secret_file(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8").strip()
    except Exception:
        return None


def _raw_secret_value() -> Optional[str]:
    """
    Resolve a raw secret string from env or file (no decoding here).
    Precedence:
        1) JWT_SECRET_FILE
        2) SECRET_KEY_FILE
        3) JWT_SECRET
        4) SECRET_KEY
    Returns None if not found.
    """
    for key in ("JWT_SECRET_FILE", "SECRET_KEY_FILE"):
        p = os.getenv(key)
        if p and p.strip():
            v = _read_secret_file(p.strip())
            if v:
                return v
    for key in ("JWT_SECRET", "SECRET_KEY"):
        v = os.getenv(key)
        if v and v.strip():
            return v.strip()
    return None


def _secret() -> bytes:
    """
    Return the binary secret to use for signing/verification.
    Accepts both base64url-encoded secrets and raw strings.
    Dev fallback: random secret if none configured.
    """
    s = _raw_secret_value()
    if not s:
        # Dev-only fallback: ephemeral secret; do NOT rely on this in production.
        s = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    # Accept both raw and base64-encoded secrets
    try:
        # If it's valid base64/url-safe, decode; otherwise treat as raw
        return base64.urlsafe_b64decode(s + "===")
    except Exception:
        return s.encode("utf-8")


def _now() -> int:
    return int(time.time())


def _gen_jti() -> str:
    return _b64url_encode(os.urandom(16))


# ---------------- Low-level encode/decode ----------------
def _jwt_encode(payload: Dict[str, Any], header: Optional[Dict[str, Any]] = None) -> str:
    header = {"alg": "HS256", "typ": "JWT", **(header or {})}
    header_b64 = _b64url_encode(_json_dumps(header))
    payload_b64 = _b64url_encode(_json_dumps(payload))
    msg = f"{header_b64}.{payload_b64}".encode("ascii")
    sig_b64 = _sign(msg, _secret())
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def _jwt_decode(token: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("Invalid token structure")
    header_b64, payload_b64, sig_b64 = parts

    # Basic header decode first to verify alg (defensive; signature checked next)
    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception as e:
        raise JWTInvalidHeader(f"Invalid header: {e}")

    alg = (header.get("alg") or "").upper()
    if alg != "HS256":
        # We only support HS256 in this module
        raise JWTInvalidHeader("Unsupported alg (expected HS256)")

    msg = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = _sign(msg, _secret())
    if not hmac.compare_digest(sig_b64, expected_sig):
        raise JWTInvalidSignature("Invalid signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        raise JWTError(f"Invalid payload: {e}")

    return header, payload


# ---------------- High-level API ----------------
def issue_access_token(
    *,
    user_id: int | str,
    role: str,
    tenant_id: Optional[int],
    token_version: int,
    expires_in: Optional[int] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed access token carrying identity & RBAC data.
    """
    now = _now()
    exp_default = _env_from_minutes_or_seconds(
        "ACCESS_TOKEN_EXPIRES_SECONDS",
        default_seconds=900,
        minutes_name="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    exp = now + (expires_in or exp_default)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": exp,
        "jti": _gen_jti(),
        "role": role,
        "tid": tenant_id,
        "tv": int(token_version),
    }
    iss = os.getenv("JWT_ISSUER")
    aud = os.getenv("JWT_AUDIENCE")
    if iss:
        payload["iss"] = iss
    if aud:
        payload["aud"] = aud
    if extra_claims:
        # Don't allow overriding critical claims
        for k in ("sub", "type", "iat", "nbf", "exp", "jti", "role", "tid", "tv", "iss", "aud"):
            extra_claims.pop(k, None)
        payload.update(extra_claims)
    return _jwt_encode(payload)


def issue_refresh_token(
    *,
    user_id: int | str,
    token_version: int,
    tenant_id: Optional[int] = None,
    expires_in: Optional[int] = None,
    session_id: Optional[str] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed refresh token for obtaining new access tokens.

    Notes:
    - Store/track refresh 'jti' server-side if you want rotation or reuse detection.
    """
    now = _now()
    exp_default = _env_from_days_or_seconds(
        "REFRESH_TOKEN_EXPIRES_SECONDS",
        default_seconds=14 * 24 * 3600,
        days_name="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    exp = now + (expires_in or exp_default)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "nbf": now,
        "exp": exp,
        "jti": _gen_jti(),
        "tid": tenant_id,
        "tv": int(token_version),
    }
    if session_id:
        payload["sid"] = session_id
    iss = os.getenv("JWT_ISSUER")
    aud = os.getenv("JWT_AUDIENCE")
    if iss:
        payload["iss"] = iss
    if aud:
        payload["aud"] = aud
    if extra_claims:
        for k in ("sub", "type", "iat", "nbf", "exp", "jti", "tid", "tv", "iss", "aud", "sid"):
            extra_claims.pop(k, None)
        payload.update(extra_claims)
    return _jwt_encode(payload)


def issue_password_reset_token(
    *,
    user_id: int | str,
    token_version: int,
    expires_in: Optional[int] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a short-lived password reset token (type='pwreset') tied to the user's token_version.
    """
    now = _now()
    exp = now + (expires_in or _env_int("PASSWORD_RESET_EXPIRES_SECONDS", 900))
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "type": "pwreset",
        "iat": now,
        "nbf": now,
        "exp": exp,
        "jti": _gen_jti(),
        "tv": int(token_version),
    }
    iss = os.getenv("JWT_ISSUER")
    aud = os.getenv("JWT_AUDIENCE")
    if iss:
        payload["iss"] = iss
    if aud:
        payload["aud"] = aud
    if extra_claims:
        for k in ("sub","type","iat","nbf","exp","jti","tv","iss","aud"):
            extra_claims.pop(k, None)
        payload.update(extra_claims)
    return {"token": _jwt_encode(payload), "expires_at": exp}


def decode_and_validate(
    token: str,
    *,
    expected_type: Optional[str] = None,  # "access" | "refresh" | "pwreset"
    require_audience: bool = False,
    leeway: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Decode token, verify signature, times, and optional iss/aud/type.
    Returns the payload dict if valid; raises JWTError subclasses otherwise.
    """
    header, payload = _jwt_decode(token)

    # Header 'typ' is conventionally 'JWT'; don't fail if absent.
    if header.get("typ") not in (None, "JWT"):
        raise JWTInvalidHeader("Invalid 'typ' header")

    # Time checks
    now = _now()
    _leeway = max(0, leeway if leeway is not None else _env_int("JWT_LEEWAY_SECONDS", 30))
    exp = int(payload.get("exp", 0))
    nbf = int(payload.get("nbf", 0))
    if now > exp + _leeway:
        raise JWTExpired("Token expired")
    if now + _leeway < nbf:
        raise JWTNotYetValid("Token not yet valid")

    # Issuer / Audience checks (if configured)
    cfg_iss = os.getenv("JWT_ISSUER")
    cfg_aud = os.getenv("JWT_AUDIENCE")
    t_iss = payload.get("iss")
    t_aud = payload.get("aud")
    if cfg_iss and t_iss != cfg_iss:
        raise JWTInvalidIssuer("Issuer mismatch")
    if require_audience or cfg_aud:
        if t_aud != cfg_aud:
            raise JWTInvalidAudience("Audience mismatch")

    # Type check
    if expected_type is not None:
        if payload.get("type") not in {"access", "refresh", "pwreset"}:
            raise JWTInvalidType("Unknown token type")
        if payload.get("type") != expected_type:
            raise JWTInvalidType(f"Expected type '{expected_type}'")

    return payload


def issue_token_pair(
    *,
    user_id: int | str,
    role: str,
    tenant_id: Optional[int],
    token_version: int,
    access_expires_in: Optional[int] = None,
    refresh_expires_in: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Convenience: returns {'access_token', 'refresh_token', 'access_expires_at', 'refresh_expires_at'}.
    """
    now = _now()
    at_default = _env_from_minutes_or_seconds(
        "ACCESS_TOKEN_EXPIRES_SECONDS",
        default_seconds=900,
        minutes_name="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    rt_default = _env_from_days_or_seconds(
        "REFRESH_TOKEN_EXPIRES_SECONDS",
        default_seconds=14 * 24 * 3600,
        days_name="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    at_exp = now + (access_expires_in or at_default)
    rt_exp = now + (refresh_expires_in or rt_default)
    return {
        "access_token": issue_access_token(
            user_id=user_id,
            role=role,
            tenant_id=tenant_id,
            token_version=token_version,
            expires_in=access_expires_in,
        ),
        "refresh_token": issue_refresh_token(
            user_id=user_id,
            tenant_id=tenant_id,
            token_version=token_version,
            expires_in=refresh_expires_in,
        ),
        "access_expires_at": at_exp,
        "refresh_expires_at": rt_exp,
        "token_type": "Bearer",
    }


__all__ = [
    "JWTError",
    "JWTExpired",
    "JWTNotYetValid",
    "JWTInvalidSignature",
    "JWTInvalidType",
    "JWTInvalidIssuer",
    "JWTInvalidAudience",
    "JWTInvalidHeader",
    "issue_access_token",
    "issue_refresh_token",
    "issue_password_reset_token",
    "issue_token_pair",
    "decode_and_validate",
]
