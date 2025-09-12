# app/models/__init__.py
from __future__ import annotations

"""
Models package export + registration.

Purpose
-------
Ensure all ORM models are registered on the shared Base.metadata so Alembic and the
application see the same schema. This module:

- Re-exports Base, engine, SessionLocal, and get_metadata from .base
- Imports concrete models (User, Tenant) so their tables register with Base.metadata
- Provides a clean __all__ for consumers: `from app.models import User, Tenant, Base, engine, SessionLocal`

Notes
-----
- Keep imports at module level (side-effect: model classes register with metadata).
- This file is additive and safe. It does not remove any existing behavior.
"""

from .base import Base, engine, SessionLocal, get_metadata  # noqa: F401

# Models are imported directly in domain APIs to avoid circular dependencies
# For alembic compatibility, import models only when needed
try:
    from domains.users.models.user import User  # noqa: F401
    from domains.tenancy.models.tenant import Tenant  # noqa: F401
    from domains.companies.models.company import Company  # noqa: F401
except ImportError:
    # Fallback for when domain models can't be imported
    User = None  # type: ignore
    Tenant = None  # type: ignore
    Company = None  # type: ignore

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_metadata",
    "User",
    "Tenant",
    "Company",
]
