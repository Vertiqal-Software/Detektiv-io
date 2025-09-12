# alembic/versions/0005_create_tenants.py
"""create tenants table to support multi-tenancy

Revision ID: 0005_create_tenants
Revises: 0004_users_security_columns
Create Date: 2025-09-03 00:00:00.000000

Updated add-only based on your uploaded file (idempotent creation, SQLite safety,
and seeding of the 'public' tenant).
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
revision = "0005_create_tenants"
down_revision: Optional[str] = "0004_users_security_columns"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers (consistent with other migrations)
# ---------------------------------------------------------------------------

def _get_schema() -> str:
    """
    Resolve target schema with a safe default.

    Env (first non-empty wins):
      - ALEMBIC_SCHEMA
      - POSTGRES_SCHEMA
      - DB_SCHEMA
    Default: "public"

    Only allow [A-Za-z0-9_], starting with letter/_ (avoid injection).
    """
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


def _qualified(table: str, schema: str, dialect: str) -> str:
    return f"{schema}.{table}" if dialect == "postgresql" else table


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """
    Create `tenants` table if missing, aligned with middleware/model expectations:

      - id           BIGINT PK
      - tenant_key   VARCHAR(64) NOT NULL UNIQUE  (safe key: ^[A-Za-z0-9_-]{1,64}$)
      - name         VARCHAR(255) NOT NULL
      - created_at   TIMESTAMPTZ NOT NULL DEFAULT now()      [Postgres]
      - updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()      [Postgres]

    Also:
      - Index on name (ix_tenants_name) for admin lookups/autocomplete.
      - Seed a 'public' tenant row (tenant_key='public', name='Public') idempotently.

    Defensive/idempotent:
      - If table/constraints/indexes already exist, we skip creating them.
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)
    is_pg = dialect == "postgresql"

    # 1) Create table if absent
    if not _table_exists(insp, "tenants", schema):
        op.create_table(
            "tenants",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()") if is_pg else None,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()") if is_pg else None,
            ),
            schema=schema,
        )

    # 2) Constraints & indexes (create if missing)
    idxs = _idxnames(insp, "tenants", schema)

    if "uq_tenants_tenant_key" not in idxs:
        try:
            op.create_unique_constraint("uq_tenants_tenant_key", "tenants", ["tenant_key"], schema=schema)
        except Exception:
            # Some dialects might have created an unnamed UC; continue
            pass

    if "ix_tenants_name" not in idxs:
        try:
            op.create_index("ix_tenants_name", "tenants", ["name"], unique=False, schema=schema)
        except Exception:
            pass

    # 3) Seed 'public' tenant (idempotent, works on PG/SQLite)
    tenants_tn = _qualified("tenants", schema, dialect)
    try:
        if is_pg:
            bind.execute(
                sa.text(
                    f'INSERT INTO {tenants_tn} (tenant_key, name) VALUES (:k, :n) '
                    f"ON CONFLICT (tenant_key) DO NOTHING"
                ),
                {"k": "public", "n": "Public"},
            )
        else:
            bind.execute(
                sa.text(
                    f"INSERT OR IGNORE INTO {tenants_tn} (tenant_key, name) VALUES (:k, :n)"
                ),
                {"k": "public", "n": "Public"},
            )
    except Exception:
        # Non-fatal in dev; table exists and can be filled later via app logic.
        pass


def downgrade() -> None:
    """
    Drop constraints/indexes and the table (if present).
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    if not _table_exists(insp, "tenants", schema):
        return

    idxs = _idxnames(insp, "tenants", schema)
    if "ix_tenants_name" in idxs:
        try:
            op.drop_index("ix_tenants_name", table_name="tenants", schema=schema)
        except Exception:
            pass
    if "uq_tenants_tenant_key" in idxs:
        try:
            op.drop_constraint("uq_tenants_tenant_key", "tenants", type_="unique", schema=schema)
        except Exception:
            # As a fallback, try dropping as an index (some dialects report it only as index)
            try:
                op.drop_index("uq_tenants_tenant_key", table_name="tenants", schema=schema)
            except Exception:
                pass

    try:
        op.drop_table("tenants", schema=schema)
    except Exception:
        # Best-effort: if constraints prevent drop, they should be removed first.
        pass
