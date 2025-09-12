# app/api/companies_house.py
"""
Companies House API endpoints (backward compatibility).
Re-exports from integration implementation.
"""
from __future__ import annotations

from fastapi import APIRouter

# Import the router from the integration implementation
try:
    from integrations.companies_house.companies_house import router as ch_router

    # Create a new router for backward compatibility
    router = APIRouter(prefix="/companies-house", tags=["companies-house"])

    # Include all routes from the integration router
    router.include_router(ch_router)

except ImportError:
    # Fallback if integration router doesn't exist
    from fastapi import HTTPException

    router = APIRouter(prefix="/companies-house", tags=["companies-house"])

    @router.get("/search")
    def search_companies_house():
        raise HTTPException(
            status_code=501,
            detail="Companies House API not implemented. Please configure integration.",
        )
