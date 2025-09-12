# alembic/versions/0008_users_add_tenant_id_and_unique.py
"""users: add tenant_id and per-tenant unique email, backfill safely

Revision ID: 0008_users_add_tenant_id_and_unique
Revises: 0007_companies_add_tenant_id
Create Date: 2025-09-03 00:00:00.000000

Add-only recovery notes:
- Based on your uploaded file; behavior kept and strengthened with:
  • Drop legacy global uniques (uq_users_email, uq_users_email_lower_idx, uq_users_email_normalized_idx)
  • Create a named FK (fk_users_tenant) if missing
  • Safer backfill (leave email_normalized NULL when email is NULL)
  • Defensive existence checks for all objects; SQLite-safe paths
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
revision = "0008_users_add_tenant_id_and_unique"
down_revision: Optional[str] = "0007_companies_add_tenant_id"
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


def _colnames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    try:
        cols = inspector.get_columns(table, schema=schema)
    except TypeError:
        cols = inspector.get_columns(table)
    return {c["name"] for c in cols}


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
    Goal
    ----
    Make `users` tenant-aware and enforce per-tenant unique emails:

      1) Ensure `email_normalized` exists and is backfilled to lower(trim(email)).
         (Leave NULL when email is NULL to avoid UC conflicts.)
      2) Add nullable `tenant_id` BIGINT with FK to tenants.id when available (create FK if missing).
      3) Ensure a 'public' tenant exists; backfill users.tenant_id with its id where NULL.
      4) Drop legacy global unique constraints on email:
           - uq_users_email (0001)
           - uq_users_email_lower_idx (0003 functional unique index)
           - uq_users_email_normalized_idx (0003 fallback unique index)
      5) Add UC on (tenant_id, email_normalized): uq_users_tenant_email_norm.
      6) Add helpful index on tenant_id (ix_users_tenant_id).

    Defensive/Idempotent: skip steps when already applied.
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)
    is_pg = dialect == "postgresql"

    if not _table_exists(insp, "users", schema):
        return

    users_tn = _qualified("users", schema, dialect)
    tenants_tn = _qualified("tenants", schema, dialect)
    cols = _colnames(insp, "users", schema)
    idxs = _idxnames(insp, "users", schema)
    fks = _fknames(insp, "users", schema)
    tenants_exists = _table_exists(insp, "tenants", schema)

    # 1) email_normalized column presence + backfill
    if "email_normalized" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "email_normalized", sa.String(length=320), nullable=True, index=True
            ),
            schema=schema,
        )
        cols = _colnames(insp, "users", schema)

    # Backfill normalized (leave NULL emails as NULL)
    try:
        bind.execute(
            sa.text(
                f"UPDATE {users_tn} SET email_normalized = LOWER(TRIM(email)) "
                f"WHERE email IS NOT NULL AND (email_normalized IS NULL OR email_normalized <> LOWER(TRIM(email)))"
            )
        )
    except Exception:
        pass

    # 2) Add tenant_id (nullable) and ensure FK exists
    if "tenant_id" not in cols:
        if is_pg and tenants_exists:
            op.add_column(
                "users",
                sa.Column(
                    "tenant_id",
                    sa.BigInteger(),
                    sa.ForeignKey(f"{schema}.tenants.id", ondelete="SET NULL"),
                    nullable=True,
                ),
                schema=schema,
            )
        else:
            op.add_column(
                "users",
                sa.Column("tenant_id", sa.BigInteger(), nullable=True),
                schema=schema,
            )
        cols = _colnames(insp, "users", schema)

    # Create a named FK if tenants table exists and we don't already have one
    if tenants_exists and "fk_users_tenant" not in fks and "tenant_id" in cols:
        try:
            if is_pg:
                op.create_foreign_key(
                    "fk_users_tenant",
                    "users",
                    "tenants",
                    local_cols=["tenant_id"],
                    remote_cols=["id"],
                    source_schema=schema,
                    referent_schema=schema,
                    ondelete="SET NULL",
                )
            else:
                op.create_foreign_key(
                    "fk_users_tenant",
                    "users",
                    "tenants",
                    local_cols=["tenant_id"],
                    remote_cols=["id"],
                    ondelete="SET NULL",
                )
        except Exception:
            # Non-fatal (older SQLite, or FK already present under anonymous name)
            pass

    # 3) Ensure 'public' tenant exists and backfill tenant_id
    public_id = None
    if tenants_exists:
        try:
            row = bind.execute(
                sa.text(f"SELECT id FROM {tenants_tn} WHERE tenant_key = :k LIMIT 1"),
                {"k": "public"},
            ).fetchone()
            if row:
                public_id = int(row[0])
            else:
                # Insert if missing
                if is_pg:
                    bind.execute(
                        sa.text(
                            f"INSERT INTO {tenants_tn} (tenant_key, name) VALUES (:k, :n) "
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
                    sa.text(
                        f"SELECT id FROM {tenants_tn} WHERE tenant_key = :k LIMIT 1"
                    ),
                    {"k": "public"},
                ).fetchone()
                if row:
                    public_id = int(row[0])
        except Exception:
            public_id = None

    if "tenant_id" in cols and public_id is not None:
        try:
            bind.execute(
                sa.text(
                    f"UPDATE {users_tn} SET tenant_id = :pid WHERE tenant_id IS NULL"
                ),
                {"pid": public_id},
            )
        except Exception:
            # Non-fatal; may have users we can't backfill (leave NULL)
            pass

    # 4) Drop legacy global uniques before creating per-tenant UC

    # 4a) Drop 0001 global UNIQUE(email) if present
    if "uq_users_email" in idxs:
        try:
            op.drop_constraint("uq_users_email", "users", type_="unique", schema=schema)
        except Exception:
            # Some dialects may expose it as an index
            try:
                op.drop_index("uq_users_email", table_name="users", schema=schema)
            except Exception:
                pass

    # 4b) Drop 0003 functional unique index on lower(email) if present
    if "uq_users_email_lower_idx" in idxs:
        try:
            op.drop_index("uq_users_email_lower_idx", table_name="users", schema=schema)
        except Exception:
            try:
                op.drop_constraint(
                    "uq_users_email_lower_idx", "users", type_="unique", schema=schema
                )
            except Exception:
                pass

    # 4c) Drop 0003 fallback unique index on email_normalized if present
    idxs = _idxnames(insp, "users", schema)  # refresh
    if "uq_users_email_normalized_idx" in idxs:
        try:
            op.drop_index(
                "uq_users_email_normalized_idx", table_name="users", schema=schema
            )
        except Exception:
            try:
                op.drop_constraint(
                    "uq_users_email_normalized_idx",
                    "users",
                    type_="unique",
                    schema=schema,
                )
            except Exception:
                pass

    # 5) Add per-tenant UC on (tenant_id, email_normalized)
    idxs = _idxnames(insp, "users", schema)  # refresh
    if (
        "uq_users_tenant_email_norm" not in idxs
        and "tenant_id" in cols
        and "email_normalized" in cols
    ):
        try:
            op.create_unique_constraint(
                "uq_users_tenant_email_norm",
                "users",
                ["tenant_id", "email_normalized"],
                schema=schema,
            )
        except Exception:
            # Skip in dev if conflicting data exists; remediation needed
            pass

    # 6) Helpful index on tenant_id
    if "ix_users_tenant_id" not in idxs and "tenant_id" in cols:
        try:
            op.create_index(
                "ix_users_tenant_id",
                "users",
                ["tenant_id"],
                unique=False,
                schema=schema,
            )
        except Exception:
            pass


def downgrade() -> None:
    """
    Reverse changes best-effort:
      - Drop per-tenant UC and tenant_id-related index/FK/column
      - Recreate legacy uniques: (a) lower(email) functional unique index; (b) uq_users_email on email
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    if not _table_exists(insp, "users", schema):
        return

    idxs = _idxnames(insp, "users", schema)
    cols = _colnames(insp, "users", schema)
    fks = _fknames(insp, "users", schema)

    # Drop per-tenant UC
    if "uq_users_tenant_email_norm" in idxs:
        try:
            op.drop_constraint(
                "uq_users_tenant_email_norm", "users", type_="unique", schema=schema
            )
        except Exception:
            try:
                op.drop_index(
                    "uq_users_tenant_email_norm", table_name="users", schema=schema
                )
            except Exception:
                pass

    # Drop tenant index
    if "ix_users_tenant_id" in idxs:
        try:
            op.drop_index("ix_users_tenant_id", table_name="users", schema=schema)
        except Exception:
            pass

    # Drop FK first (if present), then tenant_id column
    if "fk_users_tenant" in fks:
        try:
            op.drop_constraint(
                "fk_users_tenant", "users", type_="foreignkey", schema=schema
            )
        except Exception:
            pass

    if "tenant_id" in cols:
        try:
            op.drop_column("users", "tenant_id", schema=schema)
        except Exception:
            pass

    # Recreate legacy uniques from earlier migrations
    idxs = _idxnames(insp, "users", schema)

    # 0003 functional unique index
    if "uq_users_email_lower_idx" not in idxs and "email" in _colnames(
        insp, "users", schema
    ):
        try:
            op.create_index(
                "uq_users_email_lower_idx",
                "users",
                [sa.text("lower(email)")],
                unique=True,
                schema=schema,
            )
        except Exception:
            pass

    # 0001 global UNIQUE(email)
    idxs = _idxnames(insp, "users", schema)
    if "uq_users_email" not in idxs and "email" in _colnames(insp, "users", schema):
        try:
            op.create_unique_constraint(
                "uq_users_email", "users", ["email"], schema=schema
            )
        except Exception:
            # Some dialects may only allow as index
            try:
                op.create_index(
                    "uq_users_email", "users", ["email"], unique=True, schema=schema
                )
            except Exception:
                pass
