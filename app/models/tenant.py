# app/models/tenant.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func, Index, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, validates

from .base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    # Aligned type with referencing FKs (users.tenant_id, companies.tenant_id)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # IMPORTANT: DB column is 'tenant_key' (not 'key'); keep it unique + indexed + NOT NULL
    tenant_key: Mapped[str] = mapped_column(
        "tenant_key",
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Stable unique tenant identifier",
    )

    # Migrations enforce NOT NULL after backfill, so reflect that here.
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Tenant display name")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Added: index on name to speed up admin lookups and autocomplete
    __table_args__ = (
        Index("ix_tenants_name", "name"),
    )

    # Back-compat alias: allow existing code to use .key while the DB column remains tenant_key
    @property
    def key(self) -> str:
        return self.tenant_key

    @key.setter
    def key(self, value: str) -> None:
        self.tenant_key = value

    # ---------------------------- Validators ---------------------------------

    @validates("tenant_key")
    def _validate_tenant_key(self, key: str, value: str) -> str:
        """Trim and sanity-check tenant_key (DB also enforces NOT NULL/unique/length)."""
        if value is None:  # DB will reject None, but catch early
            raise ValueError("tenant_key cannot be null")
        v = value.strip()
        if not v:
            raise ValueError("tenant_key cannot be empty")
        if len(v) > 64:
            raise ValueError("tenant_key must be 64 characters or fewer")
        return v

    @validates("name")
    def _validate_name(self, key: str, value: str) -> str:
        """Trim and ensure non-empty name (DB also enforces NOT NULL)."""
        if value is None:
            raise ValueError("name cannot be null")
        v = value.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v

    # --------------------------- Convenience ---------------------------------

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, tenant_key={self.tenant_key!r}, name={self.name!r})>"
