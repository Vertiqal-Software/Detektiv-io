# alembic/versions/0006_create_companies.py
"""create companies table used by API endpoints

Revision ID: 0006_create_companies
Revises: 0005_create_tenants
Create Date: 2025-09-03 00:00:00.000000

Add-only recovery notes:
- Re-chained to depend on "0005_create_tenants".
- Idempotent: every create is guarded; if the table or indexes already exist, this migration is a no-op.
- SQLite-safe defaults (timestamps without server default when not Postgres).
- Added ix_companies_name (non-unique) for faster admin/search lookups.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Set

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0006_create_companies"
down_revision: Optional[str] = "0005_create_tenants"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers (consistent with earlier migrations)
# ---------------------------------------------------------------------------
def _get_schema() -> str:
    s = (
        os.getenv("ALEMBIC_SCHEMA")
        or os.getenv("POSTGRES_SCHEMA")
        or os.getenv("DB_SCHEMA")
        or "public"
    ).strip()
    if not s:
        s = "public"
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
        raise RuntimeError(f"Invalid schema name: {s!r}")
    return s


def _insp(bind: Connection) -> Inspector:
    return sa.inspect(bind)


def _dialect(bind: Connection) -> str:
    return bind.dialect.name


def _table_exists(inspector: Inspector, table: str, schema: str) -> bool:
    try:
        return table in inspector.get_table_names(schema=schema)
    except TypeError:
        return table in inspector.get_table_names()


def _idxnames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    names: Set[str] = set()
    try:
        idxs = inspector.get_indexes(table, schema=schema)
    except TypeError:
        idxs = inspector.get_indexes(table)
    for i in idxs or []:
        n = i.get("name")
        if n:
            names.add(n)
    # include named unique constraints (PG often reports them separately)
    try:
        ucs = inspector.get_unique_constraints(table, schema=schema)
    except Exception:
        ucs = []
    for uc in ucs or []:
        n = uc.get("name")
        if n:
            names.add(n)
    return names


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
def upgrade() -> None:
    """
    Create `companies` table (id, name, website, created_at) and helpful objects:
      - UNIQUE(name) as uq_companies_name
      - INDEX(created_at) as ix_companies_created_at
      - INDEX(name) as ix_companies_name   <-- added for faster lookups

    This is intentionally minimal; later migrations will add tenant_id and
    convert uniqueness to per-tenant in 0007.
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)
    is_pg = dialect == "postgresql"

    # Table
    if not _table_exists(insp, "companies", schema):
        op.create_table(
            "companies",
            sa.Column(
                "id",
                sa.BigInteger(),
                primary_key=True,
                autoincrement=True,
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("website", sa.String(length=1024), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()") if is_pg else None,
            ),
            schema=schema,
        )

    # Constraints / Indexes (add only if missing)
    idxs = _idxnames(insp, "companies", schema)

    if "uq_companies_name" not in idxs:
        try:
            op.create_unique_constraint(
                "uq_companies_name", "companies", ["name"], schema=schema
            )
        except Exception:
            # Some dialects may already have an unnamed UC; proceed.
            pass

    if "ix_companies_created_at" not in idxs:
        try:
            op.create_index(
                "ix_companies_created_at",
                "companies",
                ["created_at"],
                unique=False,
                schema=schema,
            )
        except Exception:
            pass

    # Added: non-unique index on name to improve search/list performance
    if "ix_companies_name" not in idxs:
        try:
            op.create_index(
                "ix_companies_name", "companies", ["name"], unique=False, schema=schema
            )
        except Exception:
            pass


def downgrade() -> None:
    """
    Drop objects created by this migration (guarded by existence checks).
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    if not _table_exists(insp, "companies", schema):
        return

    idxs = _idxnames(insp, "companies", schema)

    if "ix_companies_name" in idxs:
        try:
            op.drop_index("ix_companies_name", table_name="companies", schema=schema)
        except Exception:
            pass

    if "ix_companies_created_at" in idxs:
        try:
            op.drop_index(
                "ix_companies_created_at", table_name="companies", schema=schema
            )
        except Exception:
            pass

    if "uq_companies_name" in idxs:
        # Prefer dropping as constraint; fall back to index if driver reports it that way
        try:
            op.drop_constraint(
                "uq_companies_name", "companies", type_="unique", schema=schema
            )
        except Exception:
            try:
                op.drop_index(
                    "uq_companies_name", table_name="companies", schema=schema
                )
            except Exception:
                pass

    op.drop_table("companies", schema=schema)
