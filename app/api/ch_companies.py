# app/api/ch_companies.py
from __future__ import annotations

from typing import Any, Dict, Optional  # noqa: F401
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from app.services.companies_house import (
    CompaniesHouseClient,
    CompaniesHouseError,
    _env_api_key,
)

# Use a friendly tag that groups under your existing Swagger "Companies" area.
# (If you prefer the old tag name, change tags=["companies-house-pass-through"].)
router = APIRouter(prefix="/companies-house", tags=["Companies"])


class ErrorResponse(BaseModel):
    """Minimal error shape for Swagger docs (avoid circular imports)."""
    detail: str = Field(..., example="Upstream Companies House error")


@lru_cache(maxsize=8)
def _client_for_key(api_key: str) -> CompaniesHouseClient:
    """
    Cache clients by api_key. If the key changes in the environment, a new
    cached instance will be created automatically for that key.
    """
    return CompaniesHouseClient(api_key=api_key)


def _client() -> CompaniesHouseClient:
    """
    Resolve API key from env and return a cached client instance for that key.
    Returns 503 if no key is configured or client construction fails.
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
        # Upstream construction error (e.g., invalid key format)
        raise HTTPException(status_code=503, detail=str(e))


@router.get(
    "/companies/search",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {"model": ErrorResponse, "description": "Service unavailable (missing API key)"},
    },
)
def search_companies(
    q: str = Query(..., min_length=1, description="Free-text query for company search"),
    items_per_page: int = Query(20, ge=1, le=100, description="Companies House page size"),
    start_index: int = Query(0, ge=0, description="Offset into Companies House results"),
) -> Dict[str, Any]:
    """
    Proxy to Companies House /search/companies.
    Trims input and rejects empty strings post-trim (422).
    """
    q_clean = (q or "").strip()
    if not q_clean:
        raise HTTPException(status_code=422, detail="q must not be empty")

    try:
        return _client().search_companies(
            q_clean, items_per_page=items_per_page, start_index=start_index
        )
    except CompaniesHouseError as e:
        # Translate upstream failure to a 502 Bad Gateway for your API clients
        raise HTTPException(status_code=502, detail=str(e))


@router.get(
    "/company/{company_number}",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {"model": ErrorResponse, "description": "Service unavailable (missing API key)"},
    },
)
def company_profile(
    company_number: str = Path(..., description="Companies House company number")
) -> Dict[str, Any]:
    """
    Proxy to Companies House /company/{company_number}.
    Trims number and uppercases it; rejects empty after trim (422).
    """
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    try:
        return _client().get_company_profile(num)
    except CompaniesHouseError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get(
    "/company/{company_number}/full",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        502: {"model": ErrorResponse, "description": "Upstream error"},
        503: {"model": ErrorResponse, "description": "Service unavailable (missing API key)"},
    },
)
def company_full(
    company_number: str = Path(..., description="Companies House company number"),
    max_filings: int = Query(500, ge=1, le=2000, description="Max filings to collect"),
    max_officers: int = Query(500, ge=1, le=2000, description="Max officers to collect"),
    max_psc: int = Query(500, ge=1, le=2000, description="Max PSC records to collect"),
    max_charges: int = Query(500, ge=1, le=2000, description="Max charges to collect"),
    max_uk_establishments: int = Query(500, ge=1, le=2000, description="Max branches to collect"),
) -> Dict[str, Any]:
    """
    Aggregates profile + filings + officers + PSC + charges + UK establishments
    via the CompaniesHouseClient convenience call.
    """
    num = (company_number or "").strip().upper()
    if not num:
        raise HTTPException(status_code=422, detail="company_number must not be empty")

    try:
        return _client().get_company_full(
            company_number=num,
            max_filings=max_filings,
            max_officers=max_officers,
            max_psc=max_psc,
            max_charges=max_charges,
            max_uk_establishments=max_uk_establishments,
        )
    except CompaniesHouseError as e:
        raise HTTPException(status_code=502, detail=str(e))
