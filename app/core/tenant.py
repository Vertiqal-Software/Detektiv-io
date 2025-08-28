# app/core/tenant.py
from __future__ import annotations

import re
from typing import Optional
from fastapi import Request

TENANT_HEADER = "X-Tenant-Id"
_ALLOWED = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def extract_tenant_id(request: Request) -> Optional[str]:
    """
    Extract a tenant id from the X-Tenant-Id header.
    Only allows simple slug-like values (letters, digits, underscore, dash).
    Returns None if header is missing or invalid.
    """
    raw = request.headers.get(TENANT_HEADER)
    if not raw:
        return None
    tid = raw.strip()
    if not tid or not _ALLOWED.match(tid):
        return None
    return tid
