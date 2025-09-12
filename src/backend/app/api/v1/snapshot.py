# app/api/snapshot.py
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

# Ensure module import works during app startup (keeps existing behavior)
from . import health  # noqa: F401  (import used to guarantee module load order)

# -----------------------------
# Optional rate limiting (no-op if missing)
# -----------------------------
try:
    from app.core.limiting import limit  # type: ignore
except Exception:  # pragma: no cover
    def limit(_spec: str):  # type: ignore
        def _wrap(fn):
            return fn
        return _wrap

# -----------------------------
# Optional httpx for website HEAD (skip gracefully if missing)
# -----------------------------
try:
    import httpx  # type: ignore
    _HAVE_HTTPX = True
except Exception:  # pragma: no cover
    httpx = None  # type: ignore
    _HAVE_HTTPX = False

# Prefer an async client if your repo provides one, else adapt the sync client.
AsyncClientType = Any

# 1) Try a dedicated async client if available
_async_client_ctor: Optional[Any] = None
try:  # pragma: no cover
    # hypothetical async client (only if your repo has it)
    from app.services.ch_async_client import CompaniesHouseAsyncClient as _AsyncCtor  # type: ignore

    _async_client_ctor = _AsyncCtor  # type: ignore[assignment]
except Exception:  # nosec B110 - optional component; safe to continue without it
    _async_client_ctor = None

# 2) Fallback to the canonical sync client, adapted for async usage
_sync_client_ctor: Optional[Any] = None
_CompaniesHouseError = Exception
try:
    from app.services.companies_house import (  # type: ignore
        CompaniesHouseClient as _SyncCtor,
        CompaniesHouseError as _CompaniesHouseError,  # type: ignore
    )

    _sync_client_ctor = _SyncCtor
except Exception:  # nosec B110 - optional import; safe fallback handled below
    _sync_client_ctor = None

# 3) Legacy path mentioned in comment (keep as very last resort)
if _async_client_ctor is None and _sync_client_ctor is None:
    try:  # pragma: no cover
        # FIX: correct package path (services live under app.services, not app.api.services)
        from app.services.ch_client import CompaniesHouseClient as _LegacySyncCtor  # type: ignore

        _sync_client_ctor = _LegacySyncCtor
    except Exception:  # nosec B110 - final optional fallback; endpoint still works without CH data
        pass


router = APIRouter(prefix="/snapshot", tags=["snapshot"])


class SnapshotResponse(BaseModel):
    company_number: str = Field(..., example="01234567")
    tenant: str = Field(..., example="public")
    profile: Dict[str, Any] | None = None
    officers: Dict[str, Any] | None = None
    psc: Dict[str, Any] | None = None
    filing_history: Dict[str, Any] | None = None
    website_last_modified: str | None = Field(
        None, example="Wed, 21 Oct 2015 07:28:00 GMT"
    )


class ErrorResponse(BaseModel):
    detail: str = Field(..., example="Invalid company number")


# Tenant dependency (prefer middleware import). Fallback to safe default if missing.
try:
    from app.middleware.tenant import get_tenant_id as _get_tenant_ctx  # type: ignore

    from fastapi import Request

    def tenant_dep(request: Request) -> str:  # type: ignore
        # Prefer request.state set by TenantMiddleware, fall back to header, then 'public'
        try:
            t = getattr(request.state, "tenant_id", None)
        except Exception:
            t = None
        if isinstance(t, str) and t.strip():
            return t.strip()
        hdr = (request.headers.get("X-Tenant-Id") or "").strip()
        return hdr or "public"

    def get_tenant_id() -> str:  # type: ignore
        # Uses contextvar set by TenantMiddleware; falls back to 'public'
        return _get_tenant_ctx(default="public")  # type: ignore

except Exception:
    try:
        from app.core.tenant import tenant_dep, get_tenant_id  # type: ignore
    except Exception:
        from fastapi import Request

        def tenant_dep(request: Request) -> str:  # type: ignore
            return (request.headers.get("X-Tenant-Id") or "public").strip() or "public"

        def get_tenant_id() -> str:  # type: ignore
            return "public"


# -----------------------------
# Async client resolution layer
# -----------------------------


def _build_async_client() -> AsyncClientType:
    """
    Return an async-capable client instance. Prefer a real async client if
    present; otherwise wrap the sync CompaniesHouseClient in an async adapter
    using the default executor. This keeps the route logic unchanged.
    """
    if _async_client_ctor is not None:
        try:
            return _async_client_ctor()  # real async client provided by repo
        except Exception as e:  # pragma: no cover
            raise HTTPException(status_code=503, detail=f"Companies House client unavailable: {e}")

    if _sync_client_ctor is None:
        raise HTTPException(
            status_code=503,
            detail="Companies House client unavailable; ensure services are installed.",
        )

    # Wrap the sync client in an async adapter
    try:
        sync_client = _sync_client_ctor()
    except _CompaniesHouseError as e:
        # Most common case: missing/invalid CH_API_KEY
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"Companies House client init failed: {e}")

    class _AsyncAdapter:
        def __init__(self, inner):
            self._inner = inner

        async def company_profile(self, company_number: str) -> Dict[str, Any]:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._inner.get_company_profile, company_number
            )

        async def officers(self, company_number: str) -> Dict[str, Any]:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._inner.get_company_officers, company_number
            )

        async def psc(self, company_number: str) -> Dict[str, Any]:
            """
            Combine PSC endpoints into a single dict to match the SnapshotResponse shape.
            """
            loop = asyncio.get_running_loop()

            async def _exec(fn, *args):
                return await loop.run_in_executor(None, fn, *args)

            # Fetch in parallel on threadpool
            ind, corp, legal, stmts = await asyncio.gather(
                _exec(self._inner.get_company_psc_individuals, company_number),
                _exec(self._inner.get_company_psc_corporate, company_number),
                _exec(self._inner.get_company_psc_legal_person, company_number),
                _exec(self._inner.get_company_psc_statements, company_number),
                return_exceptions=True,
            )

            def _items(val):
                return val.get("items", []) if isinstance(val, dict) else []

            return {
                "individual": _items(ind) if not isinstance(ind, Exception) else [],
                "corporate_entity": _items(corp) if not isinstance(corp, Exception) else [],
                "legal_person": _items(legal) if not isinstance(legal, Exception) else [],
                "statements": _items(stmts) if not isinstance(stmts, Exception) else [],
            }

        async def filing_history(self, company_number: str) -> Dict[str, Any]:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._inner.get_company_filing_history, company_number
            )

        async def aclose(self) -> None:
            # No-op for sync client
            try:
                self._inner.close()
            except Exception:
                pass
            return None

    return _AsyncAdapter(sync_client)


# -----------------------------
# URL + robots helpers
# -----------------------------


def _normalize_website(url: str) -> Optional[str]:
    """
    Ensure a scheme is present; default to https://. Returns None if the URL
    is obviously malformed.
    """
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    parsed = urlparse(u, scheme="https")
    # If user typed e.g. "example.com", urlparse treats it as path; fix to netloc
    if not parsed.netloc and parsed.path:
        parsed = urlparse(f"https://{u}")
    if not parsed.netloc:
        return None
    # Return normalized URL without altering path/query/fragment
    return urlunparse(parsed)


async def _safe_head(url: str) -> str | None:
    """
    Best-effort HEAD for public website metadata.
    Courtesy check robots.txt and bail if 'Disallow: /' is present.
    Respects WEBSITE_HEAD_TIMEOUT_SECONDS and WEBSITE_HEAD_USER_AGENT env vars.
    If httpx is not installed, this returns None gracefully.
    """
    if not _HAVE_HTTPX:
        return None
    try:
        normalized = _normalize_website(url)
        if not normalized:
            return None

        # Build robots.txt URL at site root
        p = urlparse(normalized)
        robots = urlunparse((p.scheme, p.netloc, "/robots.txt", "", "", ""))

        timeout_secs = float(os.getenv("WEBSITE_HEAD_TIMEOUT_SECONDS", "3") or "3")
        ua = os.getenv("WEBSITE_HEAD_USER_AGENT", "detecktiv-link-check/0.1")

        headers = {"User-Agent": ua}
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_secs), headers=headers
        ) as client:
            try:
                rbt = await client.get(robots)
                if rbt.status_code == 200 and b"Disallow: /" in rbt.content:
                    return None
            except Exception:  # nosec B110 - robots check is best-effort
                pass

            r = await client.head(normalized, follow_redirects=True)
            if r.status_code < 400:
                return r.headers.get("Last-Modified")
    except Exception:  # nosec B110 - external calls are best-effort
        return None
    return None


# -----------------------------
# Route
# -----------------------------


@router.get(
    "/{company_number}",
    response_model=SnapshotResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid company number"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
)
@limit("20/minute")
async def snapshot(
    company_number: str = Path(..., description="Companies House company number"),
    website: Optional[str] = Query(default=None, description="Public website URL"),
    dry_run: bool = Query(default=False, description="If true, skip external calls"),
    tenant: str = tenant_dep,  # dependency injects tenant id/header
):
    # Basic input hygiene; keep existing 400 semantics
    num_raw = (company_number or "").strip().upper()
    if not num_raw or len(num_raw) > 16:
        raise HTTPException(status_code=400, detail="Invalid company number")

    results: Dict[str, Any] = {
        "profile": None,
        "officers": None,
        "psc": None,
        "filing_history": None,
    }

    # If we're doing a dry run, do not construct the CH client at all (lets dry-run
    # succeed even if CH_API_KEY is not configured).
    if not dry_run:
        ch = _build_async_client()
        # Build tasks lazily so dry_run avoids any upstream calls
        tasks = [
            ch.company_profile(num_raw),
            ch.officers(num_raw),
            ch.psc(num_raw),
            ch.filing_history(num_raw),
        ]

        try:
            profile, officers, psc, filings = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            for key, val in zip(
                list(results.keys()), [profile, officers, psc, filings]
            ):
                results[key] = None if isinstance(val, Exception) else val
        finally:
            # async clients usually provide .aclose(); adapter makes this a no-op for sync
            try:
                await ch.aclose()
            except Exception:  # nosec B110 - best-effort cleanup
                pass

    last_mod = None
    if website and not dry_run:
        last_mod = await _safe_head(website)

    return SnapshotResponse(
        company_number=num_raw,
        tenant=get_tenant_id(),
        website_last_modified=last_mod,
        **results,
    )
