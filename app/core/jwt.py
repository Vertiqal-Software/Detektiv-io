# app/core/jwt.py
"""
Minimal JWT (HS256) utilities using only the standard library.

Features:
- HS256 sign/verify with base64url encoding (RFC 7515/7519 style).
- `exp` claim support with configurable expiry (minutes) from env.
- Constant-time HMAC comparison.
- No external dependencies.

Env vars:
- SECRET_KEY (required)                 e.g., set in .env
- JWT_ALGORITHM (optional)              default: HS256 (only HS256 supported here)
- ACCESS_TOKEN_EXPIRE_MINUTES (optional) default: 60
- JWT_CLOCK_SKEW_SECONDS (optional)     default: 0 (allow small skew if needed)
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None:
        return default
    try:
        n = int(v)
        return n
    except Exception:
        return default


SECRET_KEY = os.getenv("SECRET_KEY") or ""
ALGORITHM = (os.getenv("JWT_ALGORITHM") or "HS256").upper()
ACCESS_TOKEN_EXPIRE_MINUTES = _get_env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
CLOCK_SKEW = _get_env_int("JWT_CLOCK_SKEW_SECONDS", 0)

if ALGORITHM != "HS256":
    # We only implement HS256 here to avoid extra dependencies.
    # Raise early to prevent silent misconfigurations.
    raise RuntimeError("Only HS256 is supported by app.core.jwt")


# ---------------------------------------------------------------------------
# Helpers: base64url
# ---------------------------------------------------------------------------

def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(data_str: str) -> bytes:
    pad = "=" * (-len(data_str) % 4)
    return base64.urlsafe_b64decode((data_str + pad).encode("ascii"))


# ---------------------------------------------------------------------------
# JWT core
# ---------------------------------------------------------------------------

def _hs256_sign(data: bytes, key: str) -> bytes:
    return hmac.new(key.encode("utf-8"), data, hashlib.sha256).digest()


def _json_dumps(obj: Dict[str, Any]) -> bytes:
    # Compact JSON (no spaces) for deterministic signatures
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now_ts() -> int:
    return int(time.time())


def _make_header() -> Dict[str, Any]:
    return {"alg": "HS256", "typ": "JWT"}


def encode_jwt(
    payload: Dict[str, Any],
    expires_minutes: Optional[int] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Create a signed JWT with HS256. Adds/overrides 'exp' if expires_minutes is provided
    (or uses ACCESS_TOKEN_EXPIRE_MINUTES by default).
    """
    key = secret_key or SECRET_KEY
    if not key:
        raise RuntimeError("SECRET_KEY is not configured")

    # Copy to avoid mutating caller's dict
    pl = dict(payload)

    # Set exp if requested or defaulted
    minutes = ACCESS_TOKEN_EXPIRE_MINUTES if expires_minutes is None else expires_minutes
    if minutes > 0:
        exp_ts = _utc_now_ts() + (minutes * 60)
        pl["exp"] = exp_ts

    header_b64 = _b64u_encode(_json_dumps(_make_header()))
    payload_b64 = _b64u_encode(_json_dumps(pl))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _hs256_sign(signing_input, key)
    sig_b64 = _b64u_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_jwt(token: str, secret_key: Optional[str] = None, verify_exp: bool = True) -> Dict[str, Any]:
    """
    Decode and verify a JWT. Raises ValueError on any verification problem.
    Returns the decoded payload (dict) if valid.

    Validation:
    - Structure: three dot-separated parts.
    - Header alg must be HS256.
    - Signature HMAC-SHA256 must match.
    - 'exp' enforced (if present and verify_exp=True), with optional CLOCK_SKEW.
    """
    key = secret_key or SECRET_KEY
    if not key:
        raise RuntimeError("SECRET_KEY is not configured")

    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as e:
        raise ValueError("Invalid token structure") from e

    try:
        header = json.loads(_b64u_decode(header_b64))
        payload = json.loads(_b64u_decode(payload_b64))
    except Exception as e:
        raise ValueError("Invalid token encoding") from e

    if header.get("alg") != "HS256":
        raise ValueError("Unsupported algorithm")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = _hs256_sign(signing_input, key)
    try:
        provided_sig = _b64u_decode(sig_b64)
    except Exception as e:
        raise ValueError("Invalid signature encoding") from e

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Invalid signature")

    if verify_exp and "exp" in payload:
        now = _utc_now_ts()
        if now > int(payload["exp"]) + max(0, CLOCK_SKEW):
            raise ValueError("Token expired")

    return payload


# Convenience helpers commonly used by auth endpoints
def create_access_token(subject: str | int, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a standard access token with 'sub' claim and default expiration.
    subject: user id or email
    extra_claims: any additional claims (e.g., tenant_id, is_superuser)
    """
    claims: Dict[str, Any] = {"sub": str(subject)}
    if extra_claims:
        claims.update(extra_claims)
    return encode_jwt(claims)


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify an access token and return claims (raises ValueError on failure).
    """
    return decode_jwt(token, verify_exp=True)
