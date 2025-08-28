# app/core/limiting.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
import os


def _key_func(request: Request) -> str:
    # Prefer tenant or API key; fall back to IP
    return (
        request.headers.get("X-Tenant-Id")
        or request.headers.get("X-Api-Key")
        or get_remote_address(request)
    )


default_per_min = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
limiter = Limiter(
    key_func=_key_func,
    default_limits=[f"{default_per_min}/minute"],
)
