# app/__init__.py
"""
Minimal package init.

Important: DO NOT import heavy submodules here, because importing `app`
is required by tests and tooling (alembic, uvicorn). Keep side-effects to a minimum.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Optional

# Prefer the new settings location; never hard-fail package import
try:  # pragma: no cover
    from .core.config import settings  # type: ignore
except Exception:  # noqa: BLE001
    settings: Optional[Any] = None  # exported for convenience but optional

# Expose a version string without importing the app
# Commonly sourced from container/CI envs
__version__ = (
    os.getenv("APP_VERSION")
    or os.getenv("IMAGE_TAG")
    or os.getenv("GIT_COMMIT")
    or "0.0.0"
)

_logger = logging.getLogger(__name__)


def get_settings_lazy() -> Optional[Any]:
    """
    Lazily import and return settings from app.core.config without side effects
    at package import time. Returns None if not available/misconfigured.
    """
    try:
        from importlib import import_module

        core = import_module("app.core.config")
        if hasattr(core, "get_settings"):
            return core.get_settings()  # type: ignore[attr-defined]
        if hasattr(core, "settings"):
            return core.settings  # type: ignore[attr-defined]
    except Exception:
        # Avoid raising during generic tooling imports
        return None
    return None


def get_masked_database_url_lazy() -> str:
    """
    Return a masked DB URL via the config shim, if available.
    Safe for logs; does not reveal passwords.
    """
    try:
        from app.config import get_masked_database_url  # lightweight shim

        return get_masked_database_url()  # type: ignore[no-any-return]
    except Exception:
        return "postgresql+psycopg2://*** (unresolved)"


def env_name(default: str = "development") -> str:
    """
    Return a short environment name for diagnostics/logs.
    Orders of precedence are common env var names.
    """
    return (
        os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or os.getenv("ENV") or default
    )


def is_test_env() -> bool:
    """
    Heuristic to detect test mode.
    """
    return (
        os.getenv("PYTEST_CURRENT_TEST") is not None
        or os.getenv("RUN_DB_TESTS") == "1"
        or env_name("").lower() in {"test", "testing"}
    )


def ensure_logging() -> bool:
    """
    Optional convenience to configure logging if not already set up.
    Imports inside the function to avoid import-time side effects.
    Returns True if configured, False otherwise.
    """
    try:
        from app.logging_setup import setup_logging

        setup_logging()
        return True
    except Exception:
        # Do not raise at import time; silently allow caller to proceed
        return False


__all__ = [
    "settings",
    "__version__",
    "get_settings_lazy",
    "get_masked_database_url_lazy",
    "env_name",
    "is_test_env",
    "ensure_logging",
]
