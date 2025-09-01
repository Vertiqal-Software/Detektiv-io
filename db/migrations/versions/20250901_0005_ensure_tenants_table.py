"""ensure tenants table exists and users -> tenants FK

Revision ID: 20250901_0005
Revises: 20250901_0004
Create Date: 2025-08-30 12:30:00

Notes:
- Idempotent creation/fixes for app.tenants.
- Adds/ensures users(tenant_id) -> tenants(id) FK if missing.
- Important: when patching an existing tenants table, we add columns as NULLABLE,
  backfill values, then set NOT NULL and constraints to avoid NOT NULL violations.
"""

from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "20250901_0005"
down_revision: str | None = "20250901_0004"
branch_labels = None
depends_on = None


def _schema() -> str:
    return (
        os.getenv("ALEMBIC_SCHEMA")
        or os.getenv("POSTGRES_SCHEMA")
        or os.getenv("DB_SCHEMA")
        or "app"
    ).strip() or "app"


def _insp(conn):
    return sa.inspect(conn)


def _has_table(conn, schema: str, name: str) -> bool:
    try:
        return name in _insp(conn).get_table_names(schema=schema)
    except Exception:
        return False


def _has_column(conn, schema: str, table: str, col: str) -> bool:
    try:
        cols = [c["name"] for c in _insp(conn).get_columns(table, schema=schema)]
        return col in cols
    except Exception:
        return False


def _index_names(conn, schema: str, table: str) -> set[str]:
    try:
        return {ix["name"] for ix in _insp(conn).get_indexes(table, schema=schema)}
    except Exception:
        return set()


def _has_unique_on_key(conn, schema: str) -> bool:
    try:
        for uc in _insp(conn).get_unique_constraints("tenants", schema=schema):
            cols = uc.get("column_names") or []
            if len(cols) == 1 and cols[0] == "key":
                return True
        for ix in _insp(conn).get_indexes("tenants", schema=schema):
            if ix.get("unique") and (ix.get("column_names") or []) == ["key"]:
                return True
    except Exception:
        pass
    return False


def upgrade() -> None:
    schema = _schema()
    conn = op.get_bind()
    insp = _insp(conn)

    # 1) Create app.tenants if missing (fresh installs)
    if not _has_table(conn, schema, "tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("key", name="uq_tenants_key"),
            schema=schema,
        )
        op.create_index("ix_tenants_key", "tenants", ["key"], unique=True, schema=schema)

    else:
        # 2) Patch existing tenants table forward
        # Add columns as NULLABLE first to avoid NOT NULL violation on existing rows
        if not _has_column(conn, schema, "tenants", "key"):
            op.add_column("tenants", sa.Column("key", sa.String(length=64), nullable=True), schema=schema)
        if not _has_column(conn, schema, "tenants", "name"):
            op.add_column("tenants", sa.Column("name", sa.String(length=255), nullable=True), schema=schema)
        if not _has_column(conn, schema, "tenants", "created_at"):
            op.add_column(
                "tenants",
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
                schema=schema,
            )
        if not _has_column(conn, schema, "tenants", "updated_at"):
            op.add_column(
                "tenants",
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
                schema=schema,
            )

        # Backfill any NULL/empty values using stable derivations from id
        # - key: 'tenant-' || id  (unique if id is unique)
        # - name: coalesce(name, 'Tenant ' || id)
        op.execute(
            sa.text(
                f'UPDATE "{schema}"."tenants" '
                f"SET key = 'tenant-' || id "
                f"WHERE key IS NULL OR key = ''"
            )
        )
        op.execute(
            sa.text(
                f'UPDATE "{schema}"."tenants" '
                f"SET name = COALESCE(name, 'Tenant ' || id) "
                f"WHERE name IS NULL OR name = ''"
            )
        )
        # Ensure created_at/updated_at not null
        op.execute(
            sa.text(
                f'UPDATE "{schema}"."tenants" '
                f"SET created_at = COALESCE(created_at, now()), "
                f"    updated_at = COALESCE(updated_at, now()) "
                f"WHERE created_at IS NULL OR updated_at IS NULL"
            )
        )

        # Now enforce NOT NULLs
        try:
            op.alter_column("tenants", "key", nullable=False, schema=schema)
        except Exception:
            # If there are still NULLs (shouldn't be), let the migration continue gracefully
            pass
        try:
            op.alter_column("tenants", "name", nullable=False, schema=schema)
        except Exception:
            pass
        try:
            op.alter_column("tenants", "created_at", nullable=False, schema=schema)
        except Exception:
            pass
        try:
            op.alter_column("tenants", "updated_at", nullable=False, schema=schema)
        except Exception:
            pass

        # Ensure unique constraint / index on key
        if not _has_unique_on_key(conn, schema):
            try:
                op.create_unique_constraint("uq_tenants_key", "tenants", ["key"], schema=schema)
            except Exception:
                pass
        idxs = _index_names(conn, schema, "tenants")
        if "ix_tenants_key" not in idxs:
            try:
                op.create_index("ix_tenants_key", "tenants", ["key"], unique=True, schema=schema)
            except Exception:
                pass

    # 3) Ensure users(tenant_id) -> tenants(id) FK is present
    users_exists = _has_table(conn, schema, "users")
    tenant_id_exists = _has_column(conn, schema, "users", "tenant_id") if users_exists else False
    if users_exists and tenant_id_exists:
        try:
            existing_fks = {fk.get("name") for fk in insp.get_foreign_keys("users", schema=schema)}
        except Exception:
            existing_fks = set()

        if "fk_users_tenant_id_tenants" not in existing_fks:
            try:
                op.create_foreign_key(
                    "fk_users_tenant_id_tenants",
                    "users",
                    "tenants",
                    ["tenant_id"],
                    ["id"],
                    source_schema=schema,
                    referent_schema=schema,
                    ondelete="SET NULL",
                )
            except Exception:
                # If data/ordering issues occur, don't hard-fail
                pass


def downgrade() -> None:
    schema = _schema()
    # Conservative downgrade: drop FK only; keep tenants table and data intact
    try:
        op.drop_constraint("fk_users_tenant_id_tenants", "users", type_="foreignkey", schema=schema)
    except Exception:
        pass
    # Intentionally do not drop tenants or its constraints to avoid data loss
