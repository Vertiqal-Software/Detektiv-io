# app/api/companies_house.py
from __future__ import annotations

from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, HTTPException, Query, Request

# IMPORTANT:
# We import + re-export the service client here to preserve backward imports like:
#   from app.api.companies_house import CompaniesHouseClient
# even though the canonical client now lives in app.services.companies_house
from app.services.companies_house import (
    CompaniesHouseClient,
    CompaniesHouseError,
)

__all__ = [
    "router",
    # Back-compat re-exports:
    "CompaniesHouseClient",
    "CompaniesHouseError",
]

# Exported router (main.py imports this symbol)
router = APIRouter(prefix="/companies-house", tags=["companies-house"])

# Lazy singleton client (reuses session & auth)
_client: Optional[CompaniesHouseClient] = None


def get_client() -> CompaniesHouseClient:
    global _client
    if _client is None:
        _client = CompaniesHouseClient()
    return _client


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
@router.get("/companies/search")
def search_companies(
    request: Request,
    q: str = Query(..., description="Search query"),
    items_per_page: int = Query(20, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    advanced_first: bool = Query(
        True,
        description="If true, call /advanced-search/companies first then fallback to /search/companies",
    ),
) -> Dict[str, Any]:
    known = {"q", "items_per_page", "start_index", "advanced_first"}
    extra = _extra_params(request, known)
    cli = get_client()
    try:
        if advanced_first:
            try:
                return cli.search_companies_advanced(
                    q,
                    items_per_page=items_per_page,
                    start_index=start_index,
                    extra_params=extra,
                )
            except Exception:  # nosec B110
                # fallback to basic if advanced endpoint errors
                pass
        return cli.search_companies(
            q,
            items_per_page=items_per_page,
            start_index=start_index,
            extra_params=extra,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


# -------------------------------------------------------------------------
# Company profile
# -------------------------------------------------------------------------
@router.get("/company/{company_number}")
def company_profile(company_number: str) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_profile(company_number)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


# -------------------------------------------------------------------------
# Full aggregate (officers/filings/pscs/charges/… + optional enrichment)
# -------------------------------------------------------------------------
@router.get("/company/{company_number}/full")
def company_full(
    company_number: str,
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
    cli = get_client()
    try:
        return cli.get_company_full(
            company_number=company_number,
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
@router.get("/company/{company_number}/officers")
def company_officers(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_officers(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/filing-history")
def company_filing_history(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_filing_history(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/psc/individual")
def company_psc_individual(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_psc_individuals(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/psc/corporate")
def company_psc_corporate(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_psc_corporate(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/psc/legal-person")
def company_psc_legal_person(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_psc_legal_person(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/psc/statements")
def company_psc_statements(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_psc_statements(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/charges")
def company_charges(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_charges(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/insolvency")
def company_insolvency(company_number: str) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_insolvency(company_number)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/exemptions")
def company_exemptions(company_number: str) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_exemptions(company_number)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/registers")
def company_registers(company_number: str) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_company_registers(company_number)
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/company/{company_number}/uk-establishments")
def company_uk_establishments(
    company_number: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_uk_establishments(
            company_number,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)


@router.get("/officers/{officer_id}/appointments")
def officer_appointments(
    officer_id: str,
    items_per_page: int = Query(100, ge=1, le=100),
    start_index: int = Query(0, ge=0),
    max_items: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    cli = get_client()
    try:
        return cli.get_officer_appointments(
            officer_id,
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )
    except CompaniesHouseError as e:
        raise _as_http_error(e)
