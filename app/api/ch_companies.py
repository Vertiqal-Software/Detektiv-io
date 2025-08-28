# app/api/ch_companies.py
from __future__ import annotations

from typing import Any, Dict, Optional  # noqa: F401

from fastapi import APIRouter, HTTPException, Query

from app.services.companies_house import (
    CompaniesHouseClient,
    CompaniesHouseError,
    _env_api_key,
)

router = APIRouter(prefix="/companies-house", tags=["companies-house-pass-through"])


def _client() -> CompaniesHouseClient:
    key = _env_api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Companies House API key missing. Set CH_API_KEY in environment.",
        )
    try:
        return CompaniesHouseClient(api_key=key)
    except CompaniesHouseError as e:  # pragma: no cover
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/companies/search")
def search_companies(
    q: str = Query(..., min_length=1),
    items_per_page: int = Query(20, ge=1, le=100),
    start_index: int = Query(0, ge=0),
) -> Dict[str, Any]:
    try:
        return _client().search_companies(
            q, items_per_page=items_per_page, start_index=start_index
        )
    except CompaniesHouseError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/company/{company_number}")
def company_profile(company_number: str) -> Dict[str, Any]:
    try:
        return _client().get_company_profile(company_number)
    except CompaniesHouseError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/company/{company_number}/full")
def company_full(
    company_number: str,
    max_filings: int = Query(500, ge=1, le=2000),
    max_officers: int = Query(500, ge=1, le=2000),
    max_psc: int = Query(500, ge=1, le=2000),
    max_charges: int = Query(500, ge=1, le=2000),
    max_uk_establishments: int = Query(500, ge=1, le=2000),
) -> Dict[str, Any]:
    try:
        return _client().get_company_full(
            company_number=company_number,
            max_filings=max_filings,
            max_officers=max_officers,
            max_psc=max_psc,
            max_charges=max_charges,
            max_uk_establishments=max_uk_establishments,
        )
    except CompaniesHouseError as e:
        raise HTTPException(status_code=502, detail=str(e))
