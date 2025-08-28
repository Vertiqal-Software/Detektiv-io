# app/__init__.py
"""
Minimal package init.

Important: DO NOT import heavy submodules here, because importing `app`
is required by tests and tooling (alembic, uvicorn). Keep side-effects to a minimum.
"""

# Prefer the new settings location; never hard-fail package import
try:  # pragma: no cover
    from .core.config import settings  # type: ignore
except Exception:  # noqa: BLE001
    settings = None  # exported for convenience but optional

__all__ = ["settings"]
