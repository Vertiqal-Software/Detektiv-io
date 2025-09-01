# app/core/rate_limit.py
from __future__ import annotations

"""
Rate limiting bootstrap (optional but recommended).

This module is intentionally defensive:
- If SlowAPI isn't installed, everything degrades to NO-OPs (your app still runs).
- Exposes a single public object `limiter` and a helper `install_rate_limiter(app)`.
- Supports env-configurable limits without hard-coding them in routes.

Usage in your app (main.py):
    from app.core.rate_limit import install_rate_limiter
    app = FastAPI(...)
    install_rate_limiter(app)  # safe to call even if SlowAPI isn't installed

Usage in routes:
    from app.core.rate_limit import limiter
    @router.post("/login")
    @limiter.limit_env("AUTH_LOGIN", default="10/minute")  # decorator (preferred)
    def login(...): ...

Or, for ad-hoc hits (less precise; depends on request context):
    limiter.hit("AUTH_LOGIN", request)  # request is optional (no-op if missing)

Environment variables:
    RATE_LIMIT_ENABLED            -> "1"/"true" to enable globally (default: on if SlowAPI installed)
    RATE_LIMIT_DEFAULT            -> e.g. "300/minute"
    RATE_LIMIT_AUTH_LOGIN         -> e.g. "10/minute"
    RATE_LIMIT_AUTH_REFRESH       -> e.g. "60/minute"
    RATE_LIMITS                   -> CSV map, e.g. "AUTH_LOGIN=10/minute,AUTH_REFRESH=60/minute"
    RATE_LIMIT_TRUSTED_PROXIES    -> comma-separated CIDRs (not used by default get_remote_address)
"""

import os
import logging
from typing import Callable, Optional, Dict

from fastapi import FastAPI

try:
    # SlowAPI imports (if available)
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.extension import _rate_limit_exceeded_handler  # type: ignore

    _SLOWAPI_AVAILABLE = True
except Exception:  # pragma: no cover
    _SLOWAPI_AVAILABLE = False
    Limiter = object  # type: ignore
    get_remote_address = None  # type: ignore
    RateLimitExceeded = Exception  # type: ignore
    SlowAPIMiddleware = object  # type: ignore
    _rate_limit_exceeded_handler = None  # type: ignore

log = logging.getLogger("rate_limit")


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name, "") or "").strip().lower()
    if v in {"1", "true", "yes", "y"}:
        return True
    if v in {"0", "false", "no", "n"}:
        return False
    return default


def _limits_from_env() -> Dict[str, str]:
    """
    Build a simple {NAME: RATE} map from env:
      - RATE_LIMITS="AUTH_LOGIN=10/minute,AUTH_REFRESH=60/minute"
      - RATE_LIMIT_<NAME>=<RATE>
    """
    mapping: Dict[str, str] = {}
    raw = (os.getenv("RATE_LIMITS", "") or "").strip()
    if raw:
        for part in raw.split(","):
            if not part.strip():
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                k = k.strip().upper()
                v = v.strip()
                if k and v:
                    mapping[k] = v

    # Individual overrides win
    for k, v in os.environ.items():
        if not k.startswith("RATE_LIMIT_"):
            continue
        if k in {"RATE_LIMITS"}:
            continue
        name = k[len("RATE_LIMIT_") :].upper()
        val = (v or "").strip()
        if val:
            mapping[name] = val

    return mapping


class _NoopLimiter:
    """Safe drop-in when SlowAPI isn't installed or disabling is requested."""

    def limit(self, _rate: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            return func

        return decorator

    # Env-driven decorator helper
    def limit_env(self, name: str, default: Optional[str] = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            return func

        return decorator

    def hit(self, _name: str, _request=None) -> None:
        return

    def enabled(self) -> bool:
        return False


class _LimiterFacade:
    """
    Thin facade over SlowAPI's Limiter with:
      - env-driven decorator helper `.limit_env(NAME, default=...)`
      - tolerant `.hit(NAME, request=None)` that is a no-op if request is missing
    """

    def __init__(self, limiter: Limiter) -> None:  # type: ignore[name-defined]
        self._limiter = limiter
        self._env_map = _limits_from_env()
        self._default = (os.getenv("RATE_LIMIT_DEFAULT") or "").strip()

    def limit(self, rate: str) -> Callable:
        return self._limiter.limit(rate)

    def limit_env(self, name: str, default: Optional[str] = None) -> Callable:
        env_key = (name or "").strip().upper()
        rate = self._env_map.get(env_key) or default or self._default
        if not rate:
            # If no rate configured, return a no-op decorator
            def _noop(func: Callable) -> Callable:
                return func

            return _noop
        return self._limiter.limit(rate)

    def hit(self, name: str, request=None) -> None:
        """
        Manually "hit" a named limit. If you provide a request, the limiter
        will use the configured key_func (e.g., remote address) to bucket.
        Without a request, this is a safe no-op (avoids crashes).
        """
        if request is None:
            return
        env_key = (name or "").strip().upper()
        rate = self._env_map.get(env_key) or self._default
        if not rate:
            return
        try:
            # SlowAPI >= 0.1.8 supports limiter.hit(rate, request)
            self._limiter.hit(rate, request)
        except Exception:  # pragma: no cover
            # Be resilient: if the hit API changes, don't break the app
            log.debug("limiter.hit failed (ignored)", exc_info=True)

    def enabled(self) -> bool:
        return True


# Public singleton `limiter` and installer
if _SLOWAPI_AVAILABLE and _env_bool("RATE_LIMIT_ENABLED", True):
    _underlying = Limiter(key_func=get_remote_address)  # type: ignore[arg-type]
    limiter: _LimiterFacade | _NoopLimiter = _LimiterFacade(_underlying)
else:
    limiter = _NoopLimiter()


def install_rate_limiter(app: FastAPI) -> None:
    """
    Integrate rate limiting into a FastAPI app.
    Safe to call even if SlowAPI isn't available (does nothing in that case).
    """
    if isinstance(limiter, _NoopLimiter):
        log.info(
            "Rate limiting disabled or SlowAPI not installed; continuing without limits"
        )
        return

    # Attach limiter to app state (SlowAPI convention)
    try:
        app.state.limiter = limiter._limiter  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover  # nosec B110
        pass

    # Middleware & exception handler
    try:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        log.debug("Could not register RateLimitExceeded handler", exc_info=True)

    try:
        app.add_middleware(SlowAPIMiddleware)
    except Exception:  # pragma: no cover
        log.debug("Could not add SlowAPIMiddleware", exc_info=True)

    log.info("Rate limiting middleware installed")
