# app/api/__init__.py
"""
API package init.

Goals:
- Keep imports lightweight (no heavy module loads at package import time).
- Preserve back-compat: ensure 'app.api.companies_house' exports 'router'.
- Additive: also check 'app.api.ch_companies' for a 'router' alias.
- Provide lazy helpers to fetch the aggregated API router and install error handlers.

Nothing here should raise at import time; all operations are best-effort.
"""

from __future__ import annotations

from importlib import import_module
from typing import Iterable, Optional

__all__ = [
    "get_api_router",
    "install_error_handlers_lazy",
]


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
        except Exception:
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


# Best-effort router aliasing for CH modules; never raise at import time
try:
    _ensure_companies_house_router_export()
    _ensure_ch_companies_router_export()
except Exception:
    pass


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
        pass
    return False
