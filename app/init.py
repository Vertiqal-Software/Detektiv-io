# __init__.py
"""
Lightweight package initializer.

Keep this file side-effect free: do NOT import heavy submodules here.
Useful metadata and tiny helpers only.
"""
from __future__ import annotations

import os as _os

__all__ = [
    "__version__",
    "get_version",
    "env_name",
    "is_test_env",
]

# Prefer CI/container-provided values; harmless default otherwise
__version__ = (
    _os.getenv("APP_VERSION")
    or _os.getenv("IMAGE_TAG")
    or _os.getenv("GIT_COMMIT")
    or "0.0.0"
)


def get_version() -> str:
    """Return the package version string."""
    return __version__


def env_name(default: str = "development") -> str:
    """
    Return a short environment name for diagnostics/logs.
    Uses common ENV var names, falls back to `default`.
    """
    return (
        _os.getenv("ENVIRONMENT")
        or _os.getenv("APP_ENV")
        or _os.getenv("ENV")
        or default
    )


def is_test_env() -> bool:
    """
    Heuristic to detect test mode without importing test frameworks.
    """
    return (
        _os.getenv("PYTEST_CURRENT_TEST") is not None
        or _os.getenv("RUN_DB_TESTS") == "1"
        or env_name("").lower() in {"test", "testing"}
    )
