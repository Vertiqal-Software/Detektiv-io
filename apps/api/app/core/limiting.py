# app/core/limiting.py
from __future__ import annotations

"""
Rate limiting configuration using SlowAPI.

Goals
-----
- Keep existing behaviour (simple default limits; keying by tenant/API key/IP).
- Add production-grade options without breaking anything:
    * Enable/disable switch (supports both RATE_LIMIT_ENABLED and RATE_LIMIT_DISABLED).
    * Single or multiple default limits (RATE_LIMIT_DEFAULT or RATE_LIMIT_DEFAULTS).
    * Proxy-aware client IP with trusted proxy CIDR support.
    * Pluggable storage URI (Redis, memory, etc.).
    * Stable headers (X-RateLimit-*) toggle.
    * Helpers: `limit()`, `exempt()`, `is_enabled()`, `get_default_limits()`.

Environment (any optional)
--------------------------
Legacy (still supported):
  - RATE_LIMIT_PER_MINUTE=60
  - RATE_LIMIT_DEFAULTS="60/minute; 1000/hour"
  - RATE_LIMIT_STORAGE_URI="redis://redis:6379/0"
  - RATE_LIMIT_HEADERS=1
  - RATE_LIMIT_DISABLED=0

New (preferred):
  - RATE_LIMIT_ENABLED=1
  - RATE_LIMIT_DEFAULT="200/minute"
  - RATE_LIMIT_DEFAULTS="200/minute; 3000/hour"
  - RATE_LIMIT_STORAGE_URL="redis://redis:6379/0"   (alias of *_URI)
  - RATE_LIMIT_HEADERS_ENABLED=1
  - RATE_LIMIT_TRUSTED_PROXIES="10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16"
"""

import ipaddress
import os
from typing import List, Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


# ----------------------- env helpers -----------------------


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None and str(v).strip() != "" else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on", "y"}


def _split_csv(name: str) -> list[str]:
    raw = _env(name, "")
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


# ----------------------- limits config -----------------------


def _parse_limits() -> List[str]:
    """
    Determine default limits with the following precedence:
    1) RATE_LIMIT_DEFAULTS (semicolon or comma-separated)
    2) RATE_LIMIT_DEFAULT  (single limit)
    3) RATE_LIMIT_PER_MINUTE (legacy single-per-minute)
    """
    cfg_multi = _env("RATE_LIMIT_DEFAULTS")
    if cfg_multi:
        return [p for p in _split_csv("RATE_LIMIT_DEFAULTS")]
    single = _env("RATE_LIMIT_DEFAULT")
    if single:
        return [single.strip()]
    # legacy
    per_min = int(_env("RATE_LIMIT_PER_MINUTE", "60"))
    return [f"{per_min}/minute"]


def _storage_uri() -> Optional[str]:
    """
    Prefer new URL name, then legacy, then common aliases.
    """
    return (
        _env("RATE_LIMIT_STORAGE_URL")
        or _env("RATE_LIMIT_STORAGE_URI")
        or _env("REDIS_URL")
        or _env("CACHE_URL")
        or None
    )


# ----------------------- proxy-aware IP -----------------------


def _trusted_proxies() -> list[ipaddress._BaseNetwork]:
    """
    Parse CIDR/netmask ranges from RATE_LIMIT_TRUSTED_PROXIES.
    If empty, we still try X-Forwarded-For but fall back safely.
    """
    nets: list[ipaddress._BaseNetwork] = []
    for cidr in _split_csv("RATE_LIMIT_TRUSTED_PROXIES"):
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except Exception:
            # ignore invalid entries
            pass
    return nets


def _ip_in_trusted(ip_str: str, nets: list[ipaddress._BaseNetwork]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in n for n in nets)
    except Exception:
        return False


def _real_ip(request: Request) -> str:
    """
    Best-effort client IP behind proxies/CDNs.

    Order:
      - CF-Connecting-IP / True-Client-IP / X-Real-IP
      - X-Forwarded-For chain with trusted proxy awareness
      - request.client.host
      - slowapi.util.get_remote_address
    """
    for hdr in ("cf-connecting-ip", "true-client-ip", "x-real-ip"):
        val = request.headers.get(hdr)
        if val:
            return val.strip()

    xff = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    if xff:
        # RFC 7239-style list: client, proxy1, proxy2, ...
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            nets = _trusted_proxies()
            # Walk from right (closest to server) removing trusted proxies,
            # return left-most remaining as the originating client.
            # If no trusted proxies configured, return the first element.
            if nets:
                # Remove trailing trusted hops
                # e.g., [client, edge, lb] and lb/edge are trusted => client
                while parts and _ip_in_trusted(parts[-1], nets):
                    parts.pop()
            if parts:
                return parts[0]

    if request.client and request.client.host:
        return request.client.host

    try:
        return get_remote_address(request)
    except Exception:
        return "unknown"


def _auth_fingerprint(request: Request) -> Optional[str]:
    """
    Reduce Authorization header to a short, non-sensitive fingerprint to improve
    key uniqueness when API keys/tokens are used.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    try:
        scheme, value = auth.split(None, 1)
    except ValueError:
        return None
    value = value.strip()
    if not value:
        return None
    return f"{scheme.lower()}:{value[:8]}"


def _key_func(request: Request) -> str:
    """
    Prefer tenant id (multi-tenant friendliness) or API key/token, then fall back to IP.
    """
    tenant = (request.headers.get("X-Tenant-Id") or "").strip()
    api_key = (request.headers.get("X-Api-Key") or "").strip()
    auth_fp = _auth_fingerprint(request)

    if tenant:
        return f"t:{tenant}"
    if api_key:
        return f"k:{api_key}"
    if auth_fp:
        return f"a:{auth_fp}"
    return f"ip:{_real_ip(request)}"


# ----------------------- construct limiter -----------------------

# Enable/disable (new var wins; legacy override still supported)
_enabled = _env_bool("RATE_LIMIT_ENABLED", True)
if _env_bool("RATE_LIMIT_DISABLED", False):
    _enabled = False

# Headers toggle (new name wins; legacy kept)
_headers_enabled = _env_bool(
    "RATE_LIMIT_HEADERS_ENABLED", _env_bool("RATE_LIMIT_HEADERS", True)
)

_default_limits = _parse_limits()
_storage = _storage_uri()

limiter = Limiter(
    key_func=_key_func,
    default_limits=_default_limits,
    headers_enabled=_headers_enabled,
    storage_uri=_storage if _storage else None,
    enabled=_enabled,
)

# ----------------------- helpers -----------------------


def limit(spec: str):
    """
    Convenience decorator to apply a specific limit to a route:
        @app.get("/path")
        @limit("10/second")
        def handler(): ...
    """
    return limiter.limit(spec)


def exempt(func):
    """
    Convenience decorator to exempt a route from limiting:
        @app.get("/health")
        @exempt
        def health(): ...
    """
    return limiter.exempt(func)


def is_enabled() -> bool:
    return _enabled


def get_default_limits() -> list[str]:
    return list(_default_limits)


__all__ = ["limiter", "limit", "exempt", "is_enabled", "get_default_limits"]
