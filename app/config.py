"""
Back-compat shim so legacy 'app.config' imports keep working.

Source of truth is app/core/config.py. Do not add new logic here.
This module only proxies and provides minimal, additive helpers (masking/logging).
"""

from importlib import import_module
from urllib.parse import quote_plus
import os
import warnings
import logging
from typing import Optional

# Module-local logger (inherits root config)
logger = logging.getLogger(__name__)

# Re-export everything defined in core.config (primary source of truth)
try:
    from .core.config import *  # noqa: F401,F403
except Exception as e:
    warnings.warn(
        f"[app.config] Failed to import from app.core.config ({e}). "
        "Falling back to minimal env-based shims. Please fix app/core/config.py.",
        RuntimeWarning,
    )
    logger.warning(
        "[app.config] Could not import app.core.config; using fallback shims.",
        exc_info=True
    )

# Explicit symbols commonly expected by callers
try:
    from .core.config import Settings  # type: ignore
except Exception:
    Settings = None  # type: ignore

try:
    from .core.config import get_settings  # type: ignore
except Exception:
    get_settings = None  # type: ignore

try:
    from .core.config import settings  # type: ignore
except Exception:
    settings = None  # type: ignore


def _build_url_from_pg_env() -> str:
    """Fallback DSN builder if core.config doesn't provide one."""
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "detecktiv")
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{database}?sslmode={sslmode}"
    )


def get_database_url() -> str:
    """
    Back-compat helper used by Alembic or any legacy code that expects
    app.config.get_database_url(). Prefer app.core.config.settings.get_database_url(),
    fall back to env-based construction.
    """
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    if settings and hasattr(settings, "get_database_url"):
        try:
            return settings.get_database_url()  # type: ignore[attr-defined]
        except Exception:
            # Avoid blocking runtime if user-provided settings are misconfigured
            logger.debug(
                "[app.config] settings.get_database_url() raised; falling back to env.",
                exc_info=True
            )

    return _build_url_from_pg_env()


# ----------------------------
# ADDITIVE: Safe masking helpers
# ----------------------------

def _mask_url_password(url: str) -> str:
    """
    Mask the password portion of a SQLAlchemy-style URL for safe logging.
    Works for schemes like 'postgresql+psycopg2://user:pass@host:port/db?x=y'.
    If structure is unexpected, returns the original string.
    """
    try:
        scheme_sep = "://"
        si = url.find(scheme_sep)
        if si == -1:
            return url
        start = si + len(scheme_sep)
        at = url.find("@", start)
        if at == -1:
            return url
        colon = url.find(":", start)
        if colon == -1 or colon > at:
            return url
        # Replace password between first colon (after scheme) and '@'
        return url[:colon + 1] + "***" + url[at:]
    except Exception:
        return url


def get_masked_database_url(explicit_url: Optional[str] = None) -> str:
    """
    Return a masked database URL (password hidden) for logging/diagnostics.
    If explicit_url is not provided, resolves via get_database_url().
    """
    try:
        url = explicit_url if explicit_url is not None else get_database_url()
        return _mask_url_password(url)
    except Exception:
        return "postgresql+psycopg2://*** (unresolved)"


def log_effective_database_url(level: int = logging.INFO) -> None:
    """
    Convenience logger for the currently effective DATABASE_URL (masked).
    Useful in CI/containers where multiple layers might set connection details.
    """
    try:
        masked = get_masked_database_url()
        logger.log(level, f"[app.config] Effective DATABASE_URL: {masked}")
    except Exception:
        # Never raise from a debug logger
        logger.debug("[app.config] Failed to log effective DATABASE_URL.", exc_info=True)


def __getattr__(name: str):
    """
    Dynamic proxy: if an attribute is missing here but exists in app.core.config,
    expose it to keep old imports working.
    """
    try:
        core = import_module("app.core.config")
    except Exception as e:
        warnings.warn(
            f"[app.config] Unable to import app.core.config during getattr: {e}",
            RuntimeWarning,
        )
        logger.warning(
            "[app.config] getattr import of app.core.config failed.", exc_info=True
        )
        raise AttributeError(name)
    return getattr(core, name)
