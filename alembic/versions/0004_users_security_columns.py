# alembic/versions/0004_users_security_columns.py
"""add security/account columns to users and helpful index

Revision ID: 0004_users_security_columns
Revises: 0003_users_email_ci_unique
Create Date: 2025-09-01 00:00:00.000000
"""
from __future__ import annotations

import os
import re

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "0004_users_security_columns"
down_revision = "0003_users_email_ci_unique"
branch_labels = None
depends_on = None


def _get_schema() -> str:
    """
    Resolve the target schema from environment with a safe default.

    Env (first non-empty wins):
      - ALEMBIC_SCHEMA
      - POSTGRES_SCHEMA
      - DB_SCHEMA
    Default: "app"

    Only allow [A-Za-z0-9_], starting with letter/_ (avoid injection).
    """
    s = (
        os.getenv("ALEMBIC_SCHEMA")
        or os.getenv("POSTGRES_SCHEMA")
        or os.getenv("DB_SCHEMA")
        or "app"
    ).strip()
    if not s:
        s = "app"
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
        raise RuntimeError(f"Invalid schema name: {s!r}")
    return s


def _colnames(inspector, table: str, schema: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table, schema=schema)}


def _idxnames(inspector, table: str, schema: str) -> set[str]:
    return {i["name"] for i in inspector.get_indexes(table, schema=schema)}


def upgrade() -> None:
    """
    Align DB with the application's User model by adding the following columns
    if missing, with safe defaults:

      - failed_login_count INT NOT NULL DEFAULT 0
      - lockout_until TIMESTAMPTZ NULL
      - token_version INT NOT NULL DEFAULT 0
      - password_changed_at TIMESTAMPTZ NULL
      - last_login_at TIMESTAMPTZ NULL
      - is_superuser BOOL NOT NULL DEFAULT false
      - tenant_id BIGINT NULL (FK to tenants.id if that table exists)

    Also add a useful non-unique index:
      - ix_users_tenant_email (tenant_id, email)
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    schema = _get_schema()

    cols = _colnames(insp, "users", schema)
    idxs = _idxnames(insp, "users", schema)
    tables = set(insp.get_table_names(schema=schema))

    # ---- Columns (add only if missing) ----
    if "failed_login_count" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            schema=schema,
        )

    if "lockout_until" not in cols:
        op.add_column(
            "users",
            sa.Column("lockout_until", sa.DateTime(timezone=True), nullable=True),
            schema=schema,
        )

    if "token_version" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            schema=schema,
        )

    if "password_changed_at" not in cols:
        op.add_column(
            "users",
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
            schema=schema,
        )

    if "last_login_at" not in cols:
        op.add_column(
            "users",
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            schema=schema,
        )

    if "is_superuser" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "is_superuser",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            schema=schema,
        )

    # tenant_id with optional FK if tenants table exists
    if "tenant_id" not in cols:
        if "tenants" in tables:
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

    # ---- Backfill sanity (ensure non-null counters where column pre-existed but had NULLs) ----
    # (These are safe no-ops if columns were just added with defaults.)
    if "failed_login_count" in _colnames(insp, "users", schema):
        bind.execute(
            sa.text(
                f"UPDATE {schema}.users SET failed_login_count = 0 WHERE failed_login_count IS NULL"
            )
        )
    if "token_version" in _colnames(insp, "users", schema):
        bind.execute(
            sa.text(
                f"UPDATE {schema}.users SET token_version = 0 WHERE token_version IS NULL"
            )
        )
    if "is_active" in _colnames(insp, "users", schema):
        # Make sure is_active has no NULLs (expected NOT NULL TRUE in model)
        bind.execute(
            sa.text(
                f"UPDATE {schema}.users SET is_active = TRUE WHERE is_active IS NULL"
            )
        )

    # ---- Indexes (create if missing) ----
    if "ix_users_tenant_email" not in idxs:
        op.create_index(
            "ix_users_tenant_email",
            "users",
            ["tenant_id", "email"],
            unique=False,
            schema=schema,
        )


def downgrade() -> None:
    """
    Drop the index and columns introduced by this migration, but only if present.
    (Conditional drops keep downgrade idempotent if the schema was partially present.)
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    schema = _get_schema()

    idxs = _idxnames(insp, "users", schema)
    if "ix_users_tenant_email" in idxs:
        op.drop_index("ix_users_tenant_email", table_name="users", schema=schema)

    cols = _colnames(insp, "users", schema)

    # Drop tenant_id first to avoid FK dependency issues
    if "tenant_id" in cols:
        op.drop_column("users", "tenant_id", schema=schema)

    if "is_superuser" in cols:
        op.drop_column("users", "is_superuser", schema=schema)

    if "last_login_at" in cols:
        op.drop_column("users", "last_login_at", schema=schema)

    if "password_changed_at" in cols:
        op.drop_column("users", "password_changed_at", schema=schema)

    if "token_version" in cols:
        op.drop_column("users", "token_version", schema=schema)

    if "lockout_until" in cols:
        op.drop_column("users", "lockout_until", schema=schema)

    if "failed_login_count" in cols:
        op.drop_column("users", "failed_login_count", schema=schema)
