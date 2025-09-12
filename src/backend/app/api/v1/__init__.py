# app/api/__init__.py
"""
API package init.

Goals
-----
- Keep imports lightweight (no heavy module loads at package import time).
- Preserve back-compat: ensure 'app.api.companies_house' exports 'router'.
- Additive: also check 'app.api.ch_companies' for a 'router' alias.
- Provide lazy helpers to fetch routers without hard-failing if optional modules are missing.
- NEW (add-only): extend aliasing coverage to other modules ('users', 'companies',
  'snapshot', 'auth', 'metrics') in case they export non-standard names.

Nothing here should raise at import time; all operations are best-effort.
"""

from __future__ import annotations

from importlib import import_module
from typing import Iterable, Optional, List, Tuple, Any, Sequence

__all__ = [
    # Existing
    "get_api_router",
    "install_error_handlers_lazy",
    "ensure_router_aliases",
    "get_router_lazy",
    "get_default_routers",
    "include_default_routers",
    # New (add-only) convenience helpers
    "get_router_or_none",
    "list_available_routers",
]


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _ensure_router_export(module_name: str, candidates: Iterable[str]) -> None:
    """
    Ensure a module exposes a 'router' attribute, aliasing from the first
    available candidate name. Never raises.
    """
    try:
        mod = import_module(module_name)
    except Exception:
        return

    if hasattr(mod, "router"):
        return

    for alt in candidates:
        try:
            if hasattr(mod, alt):
                setattr(mod, "router", getattr(mod, alt))
                break
        except Exception:  # nosec B112
            # Continue trying other candidates
            continue


def _ensure_companies_house_router_export() -> None:
    """
    Back-compat: some historical modules may have named the router differently.
    Try common alternatives and alias to 'router'.
    """
    _ensure_router_export(
        "app.api.companies_house",
        candidates=("companies_house_router", "ch_router", "api_router"),
    )


def _ensure_ch_companies_router_export() -> None:
    """
    Additive: cover the CH pass-through module too, in case its router
    is exposed under a different name.
    """
    _ensure_router_export(
        "app.api.ch_companies",
        candidates=("ch_companies_router", "companies_house_router", "api_router"),
    )


# --- NEW: extend aliasing for other well-known app routers (safe, idempotent) ---

def _ensure_generic_router_exports() -> None:
    alias_map = {
        # module -> candidate attribute names that might exist
        "app.api.users": ("users_router", "api_router", "routes"),
        "app.api.companies": ("companies_router", "api_router", "routes"),
        "app.api.snapshot": ("snapshot_router", "api_router", "routes"),
        "app.api.auth": ("auth_router", "api_router", "routes"),
        "app.api.metrics": ("metrics_router", "api_router", "routes"),
    }
    for mod, candidates in alias_map.items():
        _ensure_router_export(mod, candidates)


def ensure_router_aliases() -> None:
    """
    Public, idempotent call to enforce router aliasing on Companies House modules
    and other common API modules in this project.
    Safe to call multiple times.
    """
    try:
        _ensure_companies_house_router_export()
        _ensure_ch_companies_router_export()
        _ensure_generic_router_exports()  # NEW
    except Exception:
        # Keep silent in production; these are best-effort conveniences.
        import logging
        logging.getLogger(__name__).debug(
            "swallowed exception (benign path) in app.api.ensure_router_aliases",
            exc_info=True,
        )


# Run aliasing once at import (benign; keeps old code working)
ensure_router_aliases()


# ---------------------------------------------------------------------------
# Public, lazy helpers
# ---------------------------------------------------------------------------

def get_api_router():
    """
    Lazily import and return the aggregated API router.
    Usage:
        from app.api import get_api_router
        app.include_router(get_api_router())
    """
    try:
        mod = import_module("app.api.router")
        return getattr(mod, "api_router")
    except Exception:
        # Return a minimal empty router to avoid breaking callers
        from fastapi import APIRouter  # lightweight

        return APIRouter()


def install_error_handlers_lazy(app) -> bool:
    """
    Lazily install custom error handlers if available.
    Returns True if installed, False if the installer wasn't found.
    Usage:
        from app.api import install_error_handlers_lazy
        install_error_handlers_lazy(app)
    """
    try:
        mod = import_module("app.api.errors")
        installer = getattr(mod, "install_error_handlers", None)
        if callable(installer):
            installer(app)
            return True
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "swallowed exception (benign path) in app.api.__init__", exc_info=True
        )
    return False


def get_router_lazy(
    module_paths: Iterable[str],
    attr_candidates: Iterable[str] = ("router", "api_router"),
):
    """
    Try several module paths and attribute names to retrieve a FastAPI router.
    Returns the first router found, or None if none can be imported.

    Example:
        r = get_router_lazy(["app.api.ch_companies", "app.api.companies_house"])
        if r:
            app.include_router(r)
    """
    for mod_name in module_paths:
        try:
            mod = import_module(mod_name)
        except Exception:
            continue
        for attr in attr_candidates:
            try:
                r = getattr(mod, attr, None)
                if r is not None:
                    return r
            except Exception:
                continue
    return None


def _try_import(path: str, attr: str) -> Tuple[str, Optional[Any]]:
    try:
        mod = import_module(path)
        val = getattr(mod, attr, None)
        return (path, val)
    except Exception:
        return (path, None)


def get_default_routers() -> List[Tuple[str, Optional[Any]]]:
    """
    Attempt to load the most common routers used by the app.
    Returns a list of (qualified_module_name, router_or_None).
    This function never raises and does not import heavy dependencies.
    """
    ensure_router_aliases()

    # Common routers we expose or use in app.main
    targets = [
        ("app.api.companies", "router"),
        # Prefer ch_companies; fallback module handled by aliasing earlier.
        ("app.api.ch_companies", "router"),
        ("app.api.snapshot", "router"),
        ("app.api.auth", "router"),
        ("app.api.metrics", "router"),
        # NEW: users router (add-only)
        ("app.api.users", "router"),
    ]
    out: List[Tuple[str, Optional[Any]]] = []
    for path, attr in targets:
        out.append(_try_import(path, attr))
    return out


def include_default_routers(app) -> List[str]:
    """
    Include a standard set of routers on the given FastAPI app.
    Returns a list of module names that were successfully included.
    This is optional; app.main typically performs explicit includes already.
    """
    included: List[str] = []
    for mod_name, router in get_default_routers():
        try:
            if router is not None:
                app.include_router(router)  # type: ignore[arg-type]
                included.append(mod_name)
        except Exception:
            # Best-effort: skip failures silently
            continue
    return included


# --- NEW: single-module convenience helpers (do not raise) -------------------

def get_router_or_none(
    module_path: str,
    attr_candidates: Sequence[str] = ("router", "api_router"),
) -> Optional[Any]:
    """
    Import a single module and return its router or None.
    Useful for guarded includes:
        r = get_router_or_none("app.api.users")
        if r: app.include_router(r)
    """
    try:
        mod = import_module(module_path)
    except Exception:
        return None
    for attr in attr_candidates:
        try:
            r = getattr(mod, attr, None)
            if r is not None:
                return r
        except Exception:
            continue
    return None


def list_available_routers() -> List[str]:
    """
    Return a list of module paths for which a router was found (best-effort).
    Helpful for diagnostics in /readiness or startup logs.
    """
    found: List[str] = []
    for mod_name, router in get_default_routers():
        if router is not None:
            found.append(mod_name)
    return found
