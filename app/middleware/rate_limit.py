"""
Simple, dependency-free rate limiting middleware for FastAPI/Starlette.

- Limits per (client_ip, path, tenant) within a fixed time window
- Adds standard rate-limit headers:
  X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After
- Skips health/docs/metrics endpoints by default
- Reads configuration from environment variables (with safe defaults)
- Stores counters in-memory (suited for dev/single-worker); no PII persisted

Env vars (documented in your repo docs):
  RATE_LIMIT_REQUESTS (default: 100)                   # requests per window
  RATE_LIMIT_WINDOW_SECONDS (default: 60)              # window length
  RATE_LIMIT_EXCLUDE_PATHS (comma-separated patterns)  # e.g., "/health,/docs"
  RATE_LIMIT_TRUST_PROXY (default: "0")                # if "1", use X-Forwarded-For

Security note (GDPR):
  IP addresses can be personal data. This middleware keeps only ephemeral,
  in-memory counters and does not persist logs of client IPs.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("app.middleware.rate_limit")


@dataclass(frozen=True)
class _Config:
    limit: int
    window: int
    exclude: Tuple[str, ...]
    trust_proxy: bool
    max_entries: int = 50_000  # cap to prevent unbounded memory growth
    cleanup_every: int = 5_000 # prune old buckets occasionally


def _load_config() -> _Config:
    def _int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            val = int(raw)
            if val <= 0:
                raise ValueError
            return val
        except ValueError:
            logger.warning("Invalid %s=%r; falling back to %d", name, raw, default)
            return default

    limit = _int("RATE_LIMIT_REQUESTS", 100)  # matches docs templates
    window = _int("RATE_LIMIT_WINDOW_SECONDS", 60)

    exclude_raw = os.getenv("RATE_LIMIT_EXCLUDE_PATHS", "").strip()
    exclude = tuple(
        p.strip() for p in exclude_raw.split(",") if p.strip()
    ) or ("/health", "/health/db", "/health/ready", "/metrics", "/docs", "/openapi.json")

    trust_proxy = os.getenv("RATE_LIMIT_TRUST_PROXY", "0").strip() in {"1", "true", "True"}

    return _Config(
        limit=limit,
        window=window,
        exclude=exclude,
        trust_proxy=trust_proxy,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Fixed-window limiter keyed by (client_ip, path, tenant).

    Implementation details:
      - In-memory dict: key -> (count, reset_epoch_seconds)
      - Occasional cleanup to drop expired windows & cap size
      - Thread-safety: asyncio.Lock to serialize updates
      - Adds headers on both allowed and limited responses
    """
    def __init__(self, app):
        super().__init__(app)
        self.cfg = _load_config()
        self._buckets: Dict[Tuple[str, str, str], Tuple[int, float]] = {}
        self._lock = asyncio.Lock()
        self._ops = 0  # for periodic cleanup

        logger.info(
            "RateLimitMiddleware enabled: limit=%d, window=%ds, exclude=%s, trust_proxy=%s",
            self.cfg.limit, self.cfg.window, list(self.cfg.exclude), self.cfg.trust_proxy
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip non-HTTP scopes or websocket
        if request.scope.get("type") != "http":
            return await call_next(request)

        # Skip OPTIONS, HEAD by default
        if request.method in {"OPTIONS", "HEAD"}:
            return await call_next(request)

        path = request.url.path

        # Exclude configured paths (prefix match)
        for p in self.cfg.exclude:
            if path.startswith(p):
                return await call_next(request)

        client_ip = self._client_ip(request)
        tenant = self._tenant_id(request)

        key = (client_ip, path, tenant)

        now = time.time()
        async with self._lock:
            count, reset_at = self._buckets.get(key, (0, now + self.cfg.window))

            # New window if expired
            if now >= reset_at:
                count = 0
                reset_at = now + self.cfg.window

            count += 1

            # Store updated bucket
            self._buckets[key] = (count, reset_at)

            self._ops += 1
            if self._ops % self.cfg.cleanup_every == 0:
                self._cleanup(now)

            # Build standard headers
            headers = {
                "X-RateLimit-Limit": str(self.cfg.limit),
                "X-RateLimit-Remaining": str(max(self.cfg.limit - count, 0)),
                "X-RateLimit-Reset": str(int(reset_at)),
            }

            # If over limit → 429
            if count > self.cfg.limit:
                retry_after = max(int(reset_at - now), 1)
                headers["Retry-After"] = str(retry_after)

                # Minimal JSON (no internals)
                payload = {
                    "detail": "Too Many Requests",
                    "status": 429,
                }
                return JSONResponse(payload, status_code=429, headers=headers)

        # Proceed and attach headers
        response = await call_next(request)
        # Avoid overwriting existing headers (if any)
        for k, v in headers.items():
            if k not in response.headers:
                response.headers[k] = v
        return response

    def _client_ip(self, request: Request) -> str:
        """
        Determine client IP.
        - If behind proxy and trust_proxy=1, use the first IP from X-Forwarded-For.
        - Otherwise, use the socket peername from ASGI scope.
        """
        if self.cfg.trust_proxy:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                ip = xff.split(",")[0].strip()
                if ip:
                    return ip

        client = request.scope.get("client")
        if client and isinstance(client, (list, tuple)) and client:
            return str(client[0])
        return "unknown"

    def _tenant_id(self, request: Request) -> str:
        """
        Pull tenant identifier from a header your stack already uses/anticipates.
        Keeping it flexible by checking a few common variants.
        """
        # Try common names you can standardize later in tenant middleware:
        for h in ("x-tenant-id", "x-tenant", "x-account-id"):
            v = request.headers.get(h)
            if v:
                return v.strip()
        return "-"  # default none

    def _cleanup(self, now: float) -> None:
        """Drop expired windows and cap dictionary size."""
        # Remove expired
        expired_keys = [k for k, (_, reset_at) in self._buckets.items() if now >= reset_at]
        for k in expired_keys:
            self._buckets.pop(k, None)

        # If still too large, drop oldest-ish (simple slice)
        if len(self._buckets) > self.cfg.max_entries:
            # Convert to list for slicing; this is approximate cleanup
            for i, k in enumerate(list(self._buckets.keys())):
                self._buckets.pop(k, None)
                if len(self._buckets) <= self.cfg.max_entries:
                    break

        logger.debug(
            "RateLimit cleanup: removed=%d, remaining=%d",
            len(expired_keys), len(self._buckets)
        )
