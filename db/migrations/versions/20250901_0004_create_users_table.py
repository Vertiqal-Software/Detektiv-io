"""create users table

Revision ID: 20250901_0004
Revises: a202509010003
Create Date: 2025-08-30 12:00:00

Notes:
- Matches app/models/user.py (BigInteger PK, unique email, optional tenant FK).
- Uses Postgres-friendly defaults (server-side timestamps; boolean defaults).
- Idempotent: creates table if missing, otherwise patches existing "users" from baseline.
"""

from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# Revision identifiers, used by Alembic.
revision: str = "20250901_0004"
down_revision: str | None = "a202509010003"
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


def _has_unique_on_email(conn, schema: str) -> bool:
    try:
        for uc in _insp(conn).get_unique_constraints("users", schema=schema):
            cols = uc.get("column_names") or []
            if len(cols) == 1 and cols[0] == "email":
                return True
        for ix in _insp(conn).get_indexes("users", schema=schema):
            if ix.get("unique") and (ix.get("column_names") or []) == ["email"]:
                return True
    except Exception:
        pass
    return False


def upgrade() -> None:
    schema = _schema()
    conn = op.get_bind()

    # If the table doesn't exist yet, create it fully (preferred path)
    if not _has_table(conn, schema, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name="fk_users_tenant_id_tenants",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint("email <> ''", name="ck_users_email_nonempty"),
            sa.UniqueConstraint("email", name="uq_users_email"),
            schema=schema,
        )
        op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False, schema=schema)
        op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"], unique=False, schema=schema)
        return

    # Otherwise, patch an existing baseline "users" table forward (idempotent).
    insp = _insp(conn)

    # 1) Ensure id is BIGINT (safe in Postgres)
    try:
        cols = insp.get_columns("users", schema=schema)
        idcol = next((c for c in cols if c["name"] == "id"), None)
        if idcol is not None:
            # If it's not already BigInteger, attempt to widen
            if not isinstance(idcol["type"], sa.BigInteger):
                op.execute(text(f'ALTER TABLE "{schema}"."users" ALTER COLUMN id TYPE BIGINT'))
    except Exception:
        # Do not hard-fail if type detection or alter isn't supported in some environments
        pass

    # 2) Add missing columns (all nullable/defaulted so backfill is safe)
    to_add: list[sa.Column] = []

    def add_if_missing(name: str, coltype, *, nullable=True, server_default=None):
        if not _has_column(conn, schema, "users", name):
            to_add.append(sa.Column(name, coltype, nullable=nullable, server_default=server_default))

    add_if_missing("full_name", sa.String(length=255), nullable=True)
    add_if_missing("hashed_password", sa.String(length=255), nullable=False)
    add_if_missing("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    add_if_missing("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    add_if_missing("tenant_id", sa.BigInteger(), nullable=True)
    add_if_missing("last_login_at", sa.DateTime(timezone=True), nullable=True)
    add_if_missing("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    # created_at likely exists from baseline; ensure updated_at exists
    add_if_missing("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    if to_add:
        op.add_column("users", to_add.pop(0), schema=schema)
        for c in to_add:
            op.add_column("users", c, schema=schema)

    # 3) Ensure FK on tenant_id
    try:
        existing_fks = {fk.get("name") for fk in insp.get_foreign_keys("users", schema=schema)}
    except Exception:
        existing_fks = set()
    if "fk_users_tenant_id_tenants" not in existing_fks and _has_column(conn, schema, "users", "tenant_id"):
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
            pass

    # 4) Ensure non-empty email check constraint
    try:
        existing_cks = {ck.get("name") for ck in insp.get_check_constraints("users", schema=schema)}
    except Exception:
        existing_cks = set()
    if "ck_users_email_nonempty" not in existing_cks:
        try:
            op.create_check_constraint("ck_users_email_nonempty", "users", "email <> ''", schema=schema)
        except Exception:
            pass

    # 5) Ensure unique on email (if baseline didn't already make one)
    if not _has_unique_on_email(conn, schema):
        try:
            op.create_unique_constraint("uq_users_email", "users", ["email"], schema=schema)
        except Exception:
            pass

    # 6) Ensure indexes
    idxs = _index_names(conn, schema, "users")
    if "ix_users_tenant_id" not in idxs and _has_column(conn, schema, "users", "tenant_id"):
        op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False, schema=schema)
    if "ix_users_tenant_email" not in idxs and _has_column(conn, schema, "users", "tenant_id"):
        op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"], unique=False, schema=schema)


def downgrade() -> None:
    schema = _schema()
    # Keep data; only drop the artifacts this migration added.
    try:
        op.drop_index("ix_users_tenant_email", table_name="users", schema=schema)
    except Exception:
        pass
    try:
        op.drop_index("ix_users_tenant_id", table_name="users", schema=schema)
    except Exception:
        pass
    try:
        op.drop_constraint("fk_users_tenant_id_tenants", "users", type_="foreignkey", schema=schema)
    except Exception:
        pass
    try:
        op.drop_constraint("ck_users_email_nonempty", "users", type_="check", schema=schema)
    except Exception:
        pass
    try:
        op.drop_constraint("uq_users_email", "users", type_="unique", schema=schema)
    except Exception:
        pass
    # Do NOT drop the users table to avoid data loss.
