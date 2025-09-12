# app/api/router.py
from __future__ import annotations

"""
Aggregated API router with domain-driven structure.

Purpose
-------
Give `app.main` a single place to include all public routers while staying
defensive: if an optional module is missing, we skip it without breaking
startup. 

New Domain Structure:
- /companies/*                           (domains/companies/api/router.py)
- /users/*                               (domains/users/api/router.py)  
- /auth/*                                (domains/users/api/router.py)
- Companies House integration            (integrations/companies_house/)

Core Infrastructure:
- /health, /healthz, /readiness          (app/api/health.py)
- /metrics                               (app/api/metrics.py)
- /snapshot/{company_number}             (app/api/snapshot.py)

Legacy Fallbacks (for backwards compatibility):
- Original endpoints from app/api/* are included as fallbacks

Notes
-----
- Domain routers bring their own tags/prefixes; we don't add extra prefixes here.
- New domain structure allows for better organization and future microservice extraction.
- Legacy endpoints are maintained for backwards compatibility during transition.
"""

from importlib import import_module
from typing import List, Optional

from fastapi import APIRouter

api_router = APIRouter()

# Keep a small record of what we successfully included for debugging/metrics
_INCLUDED: List[str] = []


def _include_if_present(module_path: str, attr: str = "router") -> Optional[str]:
    """
    Try to import a module and include its APIRouter by attribute name.
    Returns the module path if included, else None. Never raises.
    """
    try:
        mod = import_module(module_path)
        r = getattr(mod, attr, None)
        if r is not None:
            api_router.include_router(r)  # type: ignore[arg-type]
            _INCLUDED.append(module_path)
            return module_path
    except Exception:
        pass
    return None


# --- Health / readiness ---
_include_if_present("app.api.health")

# --- Metrics ---
_include_if_present("app.api.metrics")

# --- Domain-based endpoints (new structure) ---
# Companies domain
_include_if_present("domains.companies.api.router")

# Analytics domain
_include_if_present("domains.analytics.api.router")

# Auth domain
_include_if_present("domains.auth.api.router")

# Users domain (includes auth)
_include_if_present("domains.users.api.router")

# Integrations
_include_if_present("integrations.companies_house.companies_house")

# --- Simple Auth for MVP (DISABLED - using domains.auth instead) ---
# _include_if_present("app.api.simple_auth")

# --- Core infrastructure endpoints ---
# Snapshot aggregator
_include_if_present("app.api.snapshot")


def included_modules() -> List[str]:
    """
    Returns a list of module paths whose routers were included.
    Useful for logging during startup, e.g.:
        logger.info("api routers mounted: %s", included_modules())
    """
    return list(_INCLUDED)


__all__ = ["api_router", "included_modules"]
