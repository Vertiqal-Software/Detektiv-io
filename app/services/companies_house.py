# app/api/companies_house.py
from __future__ import annotations

from typing import Any, Dict, Optional, Set
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query, Request, Path, Depends
from pydantic import BaseModel, Field

# IMPORTANT:
# We import + re-export the service client here to preserve backward imports like:
#   from app.api.companies_house import CompaniesHouseClient
# even though the canonical client now lives in app.services.companies_house
from app.services.companies_house import (
    CompaniesHouseClient,
    CompaniesHouseError,
)

# Auth dependency (JWT, token_version-aware). Applied at router level below.
from app.security.deps import get_current_user

# Try to use the canonical env helper; if unavailable, fallback to raw env.
try:
    from app.services.companies_house import _env_api_key  # type: ignore
except Exception:  # pragma: no cover
    import os

    def _env_api_key() -> Optional[str]:  # type: ignore
        return os.getenv("CH_API_KEY") or os.getenv("COMPANIES_HOUSE_API_KEY")


__all__ = [
    "router",
    # Back-compat re-exports:
    "CompaniesHouseClient",
    "CompaniesHouseError",
]

# Exported router (main.py imports this symbol)
# Add auth to ALL routes via a router-level dependency; no per-endpoint changes needed.
router = APIRouter(
    prefix="/companies-house",
    tags=["companies-house"],
    dependencies=[Depends(get_current_user)],
)

# -------------------------------------------------------------------------
# Models / helpers
# -------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Minimal error shape for Swagger docs."""

    detail: str = Field(..., example="Upstream Companies House error")


@lru_cache(maxsize=8)
def _client_for_key(api_key: str) -> CompaniesHouseClient:
    """
    Cache clients by api_key. If the key changes in the environment, a new
    cached instance will be created automatically for that key.
    """
    # Prefer explicit key, so we don't depend on implicit global state.
    return CompaniesHouseClient(api_key=api_key)


def get_client() -> CompaniesHouseClient:
    """
    Resolve API key from env and return a cached client instance for that key.
    Returns 503 if no key is configured.
    """
    key = _env_api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Companies House API key missing. Set CH_API_KEY in environment.",
        )
    try:
        return _client_for_key(key)
    except CompaniesHouseError as e:  # pragma: no cover
        # Surface upstream client construction issues as 503
        raise HTTPException(status_code=503, detail=str(e))


def _extra_params(request: Request, known: Set[str]) -> Dict[str, Any]:
    """
    Collect extra query params (for pass-through filters)
    without clashing with typed args.
    """
    out: Dict[str, Any] = {}
    for k, v in request.query_params.multi_items():
        if k not in known:
            out[k] = v
    return out


def _as_http_error(exc: Exception) -> HTTPException:
    # Hide internals; surface upstream failures clearly
    return HTTPException(status_code=502, detail=str(exc))


# -------------------------------------------------------------------------
# Search (advanced first, fallback to basic)
# -------------------------------------------------------------------------
@router.get(
    "/companies/search",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def search_companies(
    request: Request,
    q: str = Query(..., description="Search query"),
    items_per_page: int = Query(
        20, ge=1, le=100, description="Companies House page size"
    ),
    start_index: int = Query(
        0, ge=0, description="Offset into Companies House results"
    ),
    advanced_first: bool = Query(
        True,
        description="If true, call /advanced-search/companies first then fallback to /search/companies",
    ),
) -> Dict[str, Any]:
    known = {"q", "items_per_page", "start_index", "advanced_first"}
    extra = _extra_params(request, known)
    q_clean = (q or "").strip()
    if not q_clean:
        raise HTTPException(status_code=422, detail="q must not be empty")

    cli = get_client()
    try:
        if advanced_first:
            try:
                return cli.search_companies_advanced(
                    q_clean,
                    items_per_page=items_per_page,
                    start_index=start_index,
                    extra_params=extra,
                )
            except Exception:  # nosec B110
                # fallback to basic if advanced endpoint errors
                pass
        return cli.search_companies(
            q_clean,
            items_per_page=items_per_page,
            start_index=start_index,
            extra_params=extra,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


# -------------------------------------------------------------------------
# Company profile
# -------------------------------------------------------------------------
@router.get(
    "/company/{company_number}",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_profile(
    company_number: str = Path(..., description="Companies House company number")
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_profile(num)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


# -------------------------------------------------------------------------
# Full aggregate (officers/filings/pscs/charges/… + optional enrichment)
# -------------------------------------------------------------------------
@router.get(
    "/company/{company_number}/full",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_full(
    company_number: str = Path(..., description="Companies House company number"),
    max_filings: int = Query(500, ge=1, le=10000),
    max_officers: int = Query(500, ge=1, le=10000),
    max_psc: int = Query(500, ge=1, le=10000),
    max_charges: int = Query(500, ge=1, le=10000),
    max_uk_establishments: int = Query(500, ge=1, le=10000),
    enrich_officer_appointments: bool = Query(
        False, description="If true, collect officer appointments (with limits below)"
    ),
    max_appointments_per_officer: int = Query(200, ge=1, le=10000),
    max_officers_for_enrichment: int = Query(50, ge=1, le=1000),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_full(
            company_number=num,
            max_filings=max_filings,
            max_officers=max_officers,
            max_psc=max_psc,
            max_charges=max_charges,
            max_uk_establishments=max_uk_establishments,
            enrich_officer_appointments=enrich_officer_appointments,
            max_appointments_per_officer=max_appointments_per_officer,
            max_officers_for_enrichment=max_officers_for_enrichment,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


# -------------------------------------------------------------------------
# Granular endpoints mirroring service methods
# -------------------------------------------------------------------------
@router.get(
    "/company/{company_number}/officers",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_officers(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_officers(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/filing-history",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_filing_history(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_filing_history(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/psc/individual",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_psc_individual(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_psc_individuals(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/psc/corporate",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_psc_corporate(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_psc_corporate(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/psc/legal-person",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_psc_legal_person(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_psc_legal_person(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/psc/statements",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_psc_statements(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_psc_statements(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/charges",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_charges(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_charges(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/insolvency",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_insolvency(
    company_number: str = Path(..., description="Companies House company number")
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_insolvency(num)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/exemptions",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_exemptions(
    company_number: str = Path(..., description="Companies House company number")
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_exemptions(num)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/registers",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_registers(
    company_number: str = Path(..., description="Companies House company number")
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_company_registers(num)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/company/{company_number}/uk-establishments",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def company_uk_establishments(
    company_number: str = Path(..., description="Companies House company number"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    cli = get_client()
    try:
        return cli.get_uk_establishments(
            num,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get(
    "/officers/{officer_id}/appointments",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {
            "model": ErrorResponse,
            "description": "Service unavailable (missing API key)",
        },
    },
)
def officer_appointments(
    officer_id: str = Path(..., description="Officer ID"),
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    oid = (officer_id or "").strip()
    if not oid:
        raise HTTPException(status_code=422, detail="officer_id must not be empty")

    cli = get_client()
    try:
        return cli.get_officer_appointments(
            oid,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)
