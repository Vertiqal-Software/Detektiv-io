# app/models/base.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy import DateTime, func, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    Adds common audit fields and simple (de)serialization helpers.
    """

    # Common timestamp fields for audit trail
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),  # DB will set this on UPDATE via the SQL function
        nullable=True,
        comment="Record last update timestamp",
    )

    def to_dict(self, exclude: Optional[Set[str]] = None) -> Dict[str, Any]:
        """
        Convert model instance to a plain dict (datetime -> ISO string).

        Args:
            exclude: field names to omit from the output
        """
        exclude = exclude or set()
        result: Dict[str, Any] = {}

        # NOTE: requires the class to be a mapped table (has __table__)
        for column in self.__table__.columns:  # type: ignore[attr-defined]
            if column.name in exclude:
                continue
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result

    def update_from_dict(
        self, data: Dict[str, Any], exclude: Optional[Set[str]] = None
    ) -> None:
        """
        Update model instance from a dict.

        Args:
            data: field -> value updates
            exclude: fields that must not be updated (immutable/sensitive)
        """
        # protect id and created_at by default
        exclude = exclude or {"id", "created_at"}
        for key, value in data.items():
            if key not in exclude and hasattr(self, key):
                setattr(self, key, value)

    def __repr__(self) -> str:
        """Compact string representation."""
        cls = self.__class__.__name__
        if hasattr(self, "id"):
            return f"<{cls}(id={getattr(self, 'id', None)})>"
        return f"<{cls}>"


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------


def _build_database_url() -> str:
    """
    Build the SQLAlchemy DSN from environment variables.

    Priority:
      1) DATABASE_URL if provided (useful in cloud hosts)
      2) Compose from POSTGRES_* variables

    IMPORTANT: In .env / .env.docker, do NOT put inline comments on the same line
               (e.g., POSTGRES_HOST=postgres # comment) because the '#' becomes
               part of the value.
    """
    # 1) Allow a full DSN override, e.g. "postgresql+psycopg2://user:pass@host:5432/db"
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # 2) Compose from discrete vars
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    db = os.getenv("POSTGRES_DB", "detecktiv")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")

    # NOTE: If your password contains special characters, consider URL-encoding
    # or using sqlalchemy.engine.URL.create instead of a raw f-string.
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL: str = _build_database_url()

# Engine & Session factory
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # drop dead connections automatically
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---------------------------------------------------------------------------
# Backwards compatibility
# ---------------------------------------------------------------------------
# Some older Alembic templates or legacy code may expect a "declarative_base()"
# style Base. We expose a separate symbol to avoid shadowing SQLAlchemy 2.0's
# DeclarativeBase used above.
LegacyBase = declarative_base()
