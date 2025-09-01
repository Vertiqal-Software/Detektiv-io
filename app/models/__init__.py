# app/models/__init__.py
"""
Model package re-exports.

This module centralizes imports so other layers can simply do:
    from app.models import Base, Company, Tenant, User

Notes:
- Keep this list in sync when adding new models so Alembic autogenerate
  (if used) can see metadata via the import chain.
- The Base import ensures target_metadata is complete for migrations.

Additions (non-breaking):
- `import_all_models()` helper to dynamically import any additional model
  modules in this package so Alembic autogenerate can discover them.
- `ensure_metadata_complete()` convenience to import all models and
  return `Base.metadata` for tooling.
"""

from .base import Base  # SQLAlchemy declarative Base / metadata
from .company import Company
from .tenant import Tenant
from .user import User

__all__ = [
    "Base",
    "Company",
    "Tenant",
    "User",
]

# ---------------------------------------------------------------------------
# Helpers (additive, safe):
# - Dynamically import all modules under app/models to ensure every mapped
#   class is registered on Base.metadata before Alembic autogenerate runs.
# - Does nothing harmful if models are already imported.
# ---------------------------------------------------------------------------

def import_all_models() -> None:
    """
    Import all Python modules in this package (except dunders and this file),
    so any Declarative models they define are registered with Base.metadata.
    """
    import pkgutil
    import importlib
    from pathlib import Path

    pkg_dir = Path(__file__).parent
    for mod_info in pkgutil.iter_modules([str(pkg_dir)]):
        name = mod_info.name
        # Skip known non-model modules and dunders; customize as needed
        if name in {"__init__", "__pycache__", "base"}:
            continue
        # Avoid re-importing the ones we already import explicitly above
        if name in {"company", "tenant", "user"}:
            continue
        try:
            importlib.import_module(f"{__name__}.{name}")
        except Exception as e:  # keep non-fatal; diagnostics only
            # You can enable logging here if desired:
            # import logging; logging.getLogger(__name__).debug("Skip %s: %s", name, e)
            pass

    # Optionally extend __all__ with any declarative models discovered dynamically.
    try:
        from sqlalchemy.orm import DeclarativeMeta  # type: ignore
        for k, v in list(globals().items()):
            if isinstance(v, DeclarativeMeta) and k not in __all__:
                __all__.append(k)
    except Exception:
        # SQLAlchemy not loaded or other edge-case; ignore silently
        pass


def ensure_metadata_complete():
    """
    Ensure all models are imported, then return Base.metadata.
    Tools (e.g., Alembic env.py) can call this to guarantee target_metadata.
    """
    import_all_models()
    return Base.metadata
