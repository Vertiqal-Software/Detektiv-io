# app/api/snapshot.py
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query

import asyncio
import httpx

# Ensure module import works during app startup (keeps existing behavior)
from . import health  # noqa: F401  (import used to guarantee module load order)

# Companies House client (expected to exist in your repo)
from .services.ch_client import CompaniesHouseClient  # type: ignore

# Tenant dependency (expected location). Fallback to safe default if missing.
try:
    from .core.tenant import tenant_dep, get_tenant_id  # type: ignore
except Exception:  # nosec B110
    # Fallbacks keep the endpoint usable if the optional module isn’t present
    from fastapi import Request

    def tenant_dep(request: Request) -> str:  # type: ignore
        return (request.headers.get("X-Tenant-Id") or "public").strip() or "public"

    def get_tenant_id() -> str:  # type: ignore
        return "public"


from pydantic import BaseModel, Field  # noqa: F401

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


class SnapshotResponse(BaseModel):
    company_number: str
    tenant: str
    profile: Dict[str, Any] | None = None
    officers: Dict[str, Any] | None = None
    psc: Dict[str, Any] | None = None
    filing_history: Dict[str, Any] | None = None
    website_last_modified: str | None = None


async def _safe_head(url: str) -> str | None:
    """
    Best-effort HEAD for public website metadata.
    Courtesy check robots.txt and bail if 'Disallow: /' is present.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            # quick robots.txt courtesy check (non-blocking if fails)
            try:
                rbt = await client.get(url.rstrip("/") + "/robots.txt")
                if rbt.status_code == 200 and b"Disallow: /" in rbt.content:
                    return None
            except Exception:  # nosec B110
                pass

            r = await client.head(url, follow_redirects=True)
            if r.status_code < 400:
                return r.headers.get("Last-Modified")
    except Exception:  # nosec B110
        return None
    return None


@router.get("/{company_number}", response_model=SnapshotResponse)
async def snapshot(
    company_number: str,
    website: Optional[str] = Query(default=None, description="Public website URL"),
    dry_run: bool = Query(default=False),
    tenant: str = tenant_dep,  # dependency injects tenant id/header
):
    if not company_number or len(company_number) > 16:
        raise HTTPException(status_code=400, detail="Invalid company number")

    ch = CompaniesHouseClient()
    tasks = [
        ch.company_profile(company_number),
        ch.officers(company_number),
        ch.psc(company_number),
        ch.filing_history(company_number),
    ]

    results: Dict[str, Any] = {
        "profile": None,
        "officers": None,
        "psc": None,
        "filing_history": None,
    }

    if not dry_run:
        try:
            profile, officers, psc, filings = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            for key, val in zip(
                list(results.keys()), [profile, officers, psc, filings]
            ):
                results[key] = None if isinstance(val, Exception) else val
        finally:
            await ch.aclose()

    last_mod = None
    if website and not dry_run:
        last_mod = await _safe_head(website)

    return SnapshotResponse(
        company_number=company_number,
        tenant=get_tenant_id(),
        website_last_modified=last_mod,
        **results,
    )
