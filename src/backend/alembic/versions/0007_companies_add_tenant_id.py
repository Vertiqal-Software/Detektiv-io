# alembic/versions/0007_companies_add_tenant_id.py
"""tenant-scope companies: add tenant_id, backfill, and per-tenant uniqueness

Revision ID: 0007_companies_add_tenant_id
Revises: 0006_create_companies
Create Date: 2025-09-03 00:00:00.000000

Add-only recovery notes:
- Based on your uploaded file; preserved behavior and identifiers, and only added
  defensive/idempotent guards (FK/index existence checks, SQLite-safe paths),
  plus a named FK for easier downgrades.
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
revision = "0007_companies_add_tenant_id"
down_revision: Optional[str] = "0006_create_companies"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers (kept consistent with prior migrations)
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


def _colnames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    try:
        cols = inspector.get_columns(table, schema=schema)
    except TypeError:
        cols = inspector.get_columns(table)
    return {c["name"] for c in cols or []}


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


def _fknames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    try:
        fks = inspector.get_foreign_keys(table, schema=schema)
    except TypeError:
        fks = inspector.get_foreign_keys(table)
    names: Set[str] = set()
    for fk in fks or []:
        n = fk.get("name")
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
    Make `companies` tenant-aware:

      1) Add nullable tenant_id BIGINT column (FK to tenants.id when available).
      2) Ensure a 'public' tenant exists; backfill companies.tenant_id with its id.
      3) Switch uniqueness from (name) -> (tenant_id, name).
      4) Add helpful indexes: ix_companies_tenant_id, ix_companies_tenant_created_at.

    All steps are defensive (skip if already applied).
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)
    is_pg = dialect == "postgresql"

    # If companies table doesn't exist, nothing to do.
    if not _table_exists(insp, "companies", schema):
        return

    cols = _colnames(insp, "companies", schema)
    idxs = _idxnames(insp, "companies", schema)
    fks = _fknames(insp, "companies", schema)
    tenants_exists = _table_exists(insp, "tenants", schema)

    # 1) Add tenant_id column (nullable), with FK when tenants table exists
    if "tenant_id" not in cols:
        op.add_column(
            "companies",
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            schema=schema,
        )
        cols = _colnames(insp, "companies", schema)

    # Create named FK if possible (helps downgrade). Guard on existence.
    if tenants_exists and "fk_companies_tenant" not in fks:
        if is_pg:
            op.create_foreign_key(
                "fk_companies_tenant",
                "companies",
                "tenants",
                local_cols=["tenant_id"],
                remote_cols=["id"],
                source_schema=schema,
                referent_schema=schema,
                ondelete="SET NULL",
            )
        else:
            # SQLite: no schema qualification
            try:
                op.create_foreign_key(
                    "fk_companies_tenant",
                    "companies",
                    "tenants",
                    local_cols=["tenant_id"],
                    remote_cols=["id"],
                    ondelete="SET NULL",
                )
            except Exception:
                # Older SQLite or disabled FKs: ignore
                pass

    # 2) Ensure a 'public' tenant exists and backfill existing companies
    companies_tn = _qualified("companies", schema, dialect)
    tenants_tn = _qualified("tenants", schema, dialect)

    public_id = None
    if tenants_exists:
        # Try to find 'public' tenant id
        try:
            row = bind.execute(
                sa.text(f"SELECT id FROM {tenants_tn} WHERE tenant_key = :k LIMIT 1"),
                {"k": "public"},
            ).fetchone()
        except Exception:
            row = None

        if row:
            public_id = int(row[0])
        else:
            # Insert 'public' tenant idempotently
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
                row = bind.execute(
                    sa.text(f"SELECT id FROM {tenants_tn} WHERE tenant_key = :k LIMIT 1"),
                    {"k": "public"},
                ).fetchone()
                if row:
                    public_id = int(row[0])
            except Exception:
                public_id = None

    # Backfill NULL tenant_id with 'public' id if we have one
    if "tenant_id" in cols and public_id is not None:
        try:
            bind.execute(
                sa.text(
                    f"UPDATE {companies_tn} SET tenant_id = :pid WHERE tenant_id IS NULL"
                ),
                {"pid": public_id},
            )
        except Exception:
            # Non-fatal; carry on (UC creation below is guarded)
            pass

    # 3) Switch uniqueness:
    #    - Drop global name UC if present
    #    - Create (tenant_id, name) UC (only when no NULL tenant_id remains)
    if "uq_companies_name" in idxs:
        try:
            op.drop_constraint("uq_companies_name", "companies", type_="unique", schema=schema)
        except Exception:
            # Some dialects may have created it as an index; attempt dropping index
            try:
                op.drop_index("uq_companies_name", table_name="companies", schema=schema)
            except Exception:
                pass

    # Only create composite UC when no NULL tenant_id remains (avoid migration failure)
    can_create_uc = True
    try:
        nulls = bind.execute(
            sa.text(f"SELECT 1 FROM {companies_tn} WHERE tenant_id IS NULL LIMIT 1")
        ).fetchone()
        if nulls:
            can_create_uc = False
    except Exception:
        can_create_uc = False

    if can_create_uc and "uq_companies_tenant_name" not in idxs:
        try:
            op.create_unique_constraint(
                "uq_companies_tenant_name",
                "companies",
                ["tenant_id", "name"],
                schema=schema,
            )
        except Exception:
            # Skip rather than failing the migration in dev
            pass

    # 4) Helpful indexes for common queries
    idxs = _idxnames(insp, "companies", schema)  # refresh
    if "ix_companies_tenant_id" not in idxs and "tenant_id" in cols:
        op.create_index(
            "ix_companies_tenant_id", "companies", ["tenant_id"], unique=False, schema=schema
        )

    if "ix_companies_tenant_created_at" not in idxs and "tenant_id" in cols and "created_at" in cols:
        op.create_index(
            "ix_companies_tenant_created_at",
            "companies",
            ["tenant_id", "created_at"],
            unique=False,
            schema=schema,
        )


def downgrade() -> None:
    """
    Downgrade steps (best-effort, defensive):
      - Drop per-tenant UC and tenant-related indexes if present.
      - Recreate global unique constraint on (name) if not present.
      - Drop FK and tenant_id column.
      - Leaves the 'public' tenant row in place (harmless).
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    if not _table_exists(insp, "companies", schema):
        return

    idxs = _idxnames(insp, "companies", schema)
    cols = _colnames(insp, "companies", schema)
    fks = _fknames(insp, "companies", schema)

    # Drop per-tenant UC
    if "uq_companies_tenant_name" in idxs:
        try:
            op.drop_constraint("uq_companies_tenant_name", "companies", type_="unique", schema=schema)
        except Exception:
            # Try as index drop if constraint not recognized
            try:
                op.drop_index("uq_companies_tenant_name", table_name="companies", schema=schema)
            except Exception:
                pass

    # Drop tenant-scoped indexes
    if "ix_companies_tenant_created_at" in idxs:
        op.drop_index("ix_companies_tenant_created_at", table_name="companies", schema=schema)
    if "ix_companies_tenant_id" in idxs:
        op.drop_index("ix_companies_tenant_id", table_name="companies", schema=schema)

    # Recreate global UC on name if missing (best-effort)
    idxs = _idxnames(insp, "companies", schema)  # refresh
    if "name" in cols and "uq_companies_name" not in idxs:
        try:
            op.create_unique_constraint("uq_companies_name", "companies", ["name"], schema=schema)
        except Exception:
            pass

    # Drop FK first (if present), then column
    if "fk_companies_tenant" in fks:
        try:
            op.drop_constraint("fk_companies_tenant", "companies", type_="foreignkey", schema=schema)
        except Exception:
            pass

    if "tenant_id" in cols:
        try:
            op.drop_column("companies", "tenant_id", schema=schema)
        except Exception:
            pass
