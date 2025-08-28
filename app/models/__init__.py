# app/models/__init__.py
"""
SQLAlchemy ORM models for the Detecktiv.io application.
"""

from .base import Base
from .company import Company

# Export all models for easy imports
__all__ = [
    "Base",
    "Company",
]

# Metadata for Alembic migrations
from .base import Base
metadata = Base.metadata