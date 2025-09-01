# app/api/router.py
from __future__ import annotations

"""
Aggregated API router for detecktiv.io

What this file does
- Creates a single APIRouter (`api_router`) that pulls in sub-routers from across the app.
- Avoids double-registration by tracking included modules.
- Lets you exclude or add modules at runtime with environment variables.
- Stays resilient if optional modules are missing (unless strict mode is enabled).

Environment knobs
- API_STRICT_IMPORTS=1           → fail-fast if an import or `router` attribute is missing
- API_ROUTER_DEBUG=1             → verbose logging of inclusions and a summary of routes
- API_EXCLUDE_MODULES="a,b,c"    → comma-separated module paths to skip
- API_EXTRA_MODULES="x,y"        → extra module paths to include at the end
- API_OPTIONAL_MODULES="x,y"     → alias for API_EXTRA_MODULES; union of both is used
"""

import logging
import os
from importlib import import_module
from typing import List, Optional, Set

from fastapi import APIRouter

api_router = APIRouter()
_log = logging.getLogger("api.router")

# Env flags
_API_STRICT_IMPORTS = (os.getenv("API_STRICT_IMPORTS", "0") == "1")
_API_ROUTER_DEBUG = (os.getenv("API_ROUTER_DEBUG", "0") == "1")

# Track modules already included to avoid accidental double-registration
_INCLUDED_MODULES: Set[str] = set()

# Parse optional excludes/extras (comma-separated module paths)
_EXCLUDE = {
    m.strip() for m in os.getenv("API_EXCLUDE_MODULES", "").split(",") if m.strip()
}
_EXTRA = {
    m.strip()
    for m in (
        os.getenv("API_EXTRA_MODULES", "")
        + ","
        + os.getenv("API_OPTIONAL_MODULES", "")
    ).split(",")
    if m.strip()
}


def _maybe_include(
    module_path: str,
    prefix: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> None:
    """
    Try to import a module and include its `router` if present.

    Notes
    - If `prefix` is provided, it's applied on top of the module's own routes.
      Most routers already define their own prefixes; avoid double-prefixing.
    - Non-fatal if the module or `router` is missing, unless API_STRICT_IMPORTS=1.
    - Skips modules listed in API_EXCLUDE_MODULES.
    - Prevents duplicate includes via _INCLUDED_MODULES registry.
    """
    if module_path in _EXCLUDE:
        if _API_ROUTER_DEBUG:
            _log.info("Excluded by env: %s", module_path)
        return

    if module_path in _INCLUDED_MODULES:
        if _API_ROUTER_DEBUG:
            _log.debug("Already included: %s (skipping duplicate)", module_path)
        return

    try:
        mod = import_module(module_path)
        r = getattr(mod, "router", None)
        if r is None:
            if _API_ROUTER_DEBUG:
                _log.debug("No 'router' in %s (skipping).", module_path)
            if _API_STRICT_IMPORTS:
                raise ImportError(f"{module_path} has no 'router'")
            return

        # Only pass prefix if provided and non-empty to avoid duplicating module-defined paths
        if prefix:
            api_router.include_router(r, prefix=prefix, tags=tags)
        else:
            api_router.include_router(r, tags=tags)

        _INCLUDED_MODULES.add(module_path)

        if _API_ROUTER_DEBUG:
            _log.info("Included router %s%s", module_path, f" (prefix={prefix})" if prefix else "")
    except Exception as e:
        if _API_ROUTER_DEBUG:
            _log.warning("Failed to include %s: %s (%s)", module_path, e, type(e).__name__)
        if _API_STRICT_IMPORTS:
            # Re-raise to fail fast in strict mode (useful during development)
            raise


# ------------------------------------------------------------------------
# Suggested inclusions
# IMPORTANT: Most modules already set their own route paths/prefixes.
# Avoid double-prefixing by omitting 'prefix=' here unless you truly want it.
# ------------------------------------------------------------------------

# Health: defines /health and /readiness itself
_maybe_include("app.api.health", tags=["Health"])

# Metrics: defines /metrics itself; do NOT add prefix or you'll get /metrics/metrics
_maybe_include("app.api.metrics", tags=["Health"])

# Companies: routes already start with /companies; avoid duplicate /companies/companies
_maybe_include("app.api.companies", tags=["Companies"])

# Companies House proxy variants:
# Both modules define their own prefixes (e.g., /companies-house); avoid extra prefixes.
_maybe_include("app.api.ch_companies", tags=["Companies"])
_maybe_include("app.api.companies_house", tags=["Companies"])

# Users & Auth: each defines its own prefix (/users and /auth); do not add a second prefix here.
_maybe_include("app.api.users", tags=["Users"])
_maybe_include("app.api.auth", tags=["Auth"])

# Optional modules (only included if present)
_maybe_include("app.api.password_reset", tags=["Auth"])       # forgot/reset flows
_maybe_include("app.api.admin_bootstrap", tags=["Admin"])     # one-time admin bootstrap
_maybe_include("app.api.snapshot", tags=["Debug"])            # /snapshot (debugging)
_maybe_include("app.api.errors", tags=["Debug"])              # may register handlers only


# ------------------------------------------------------------------------
# Optional, env-driven extras & excludes
# ------------------------------------------------------------------------
for _extra_mod in sorted(_EXTRA):
    _maybe_include(_extra_mod)


# ------------------------------------------------------------------------
# GUARANTEE critical routers exist even if lazy import failed silently
# (keeps core auth flow intact; avoids 404s if aggregator import path fails)
# ------------------------------------------------------------------------
def _force_include(module_path: str, tag: str) -> None:
    if module_path in _EXCLUDE:
        if _API_ROUTER_DEBUG:
            _log.info("Excluded by env (force step): %s", module_path)
        return

    if module_path in _INCLUDED_MODULES:
        if _API_ROUTER_DEBUG:
            _log.debug("Already included (force step): %s", module_path)
        return

    try:
        mod = import_module(module_path)
        r = getattr(mod, "router", None)
        if r:
            # No extra prefix here; routers define their own (e.g. /auth, /users)
            api_router.include_router(r, tags=[tag])
            _INCLUDED_MODULES.add(module_path)
            if _API_ROUTER_DEBUG:
                _log.info("Force-included %s", module_path)
        else:
            if _API_ROUTER_DEBUG:
                _log.warning("Force-include: %s has no 'router'", module_path)
            if _API_STRICT_IMPORTS:
                raise ImportError(f"{module_path} has no 'router'")
    except Exception as e:
        if _API_ROUTER_DEBUG:
            _log.error("Force include failed for %s: %s (%s)", module_path, e, type(e).__name__)
        if _API_STRICT_IMPORTS:
            raise


# These two are critical for auth flow and admin UX
_force_include("app.api.auth", "Auth")
_force_include("app.api.users", "Users")


def _debug_summary() -> None:
    """If debug is enabled, log a concise summary of included modules and route count."""
    if not _API_ROUTER_DEBUG:
        return
    try:
        from fastapi.routing import APIRoute

        routes = [r for r in api_router.routes if isinstance(r, APIRoute)]
        _log.info(
            "Router summary: %d included modules, %d routes",
            len(_INCLUDED_MODULES),
            len(routes),
        )
        for r in routes:
            methods = ",".join(sorted(m for m in (r.methods or set())))
            _log.debug("  %s %s  name=%s", methods, r.path, getattr(r, "name", ""))
    except Exception as e:
        _log.debug("Router summary failed: %s (%s)", e, type(e).__name__)


_debug_summary()

__all__ = ["api_router"]
