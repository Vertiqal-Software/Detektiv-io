# alembic/versions/0001_initial_users.py
"""initial users table (root of chain)

Revision ID: 0001_initial_users
Revises: None
Create Date: 2025-09-01 00:00:00.000000

Notes (add-only, safe):
- Establishes the baseline `users` table that later migrations extend.
- Columns are intentionally minimal (no roles, tenant_id, or security columns here).
- Includes a simple UNIQUE(email) which can co-exist with later CI-unique indexes.
- Idempotent: all creates/drops are guarded by introspection.
"""

from __future__ import annotations

import os
import re
from typing import Set

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0001_initial_users"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers (consistent with later migrations)
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


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """
    Create baseline `users` table:

      id              INTEGER PK
      email           VARCHAR(320) NOT NULL UNIQUE (basic, case-sensitive)
      full_name       VARCHAR(255) NULL
      password_hash   VARCHAR(512) NOT NULL
      is_active       BOOL NOT NULL DEFAULT TRUE
      created_at      TIMESTAMPTZ (PG) / DATETIME (others)
      updated_at      TIMESTAMPTZ (PG) / DATETIME (others)

    Later migrations will add:
      - roles & membership (0002)
      - case-insensitive unique email index (0003)
      - security columns & tenant_id (0004..0008)
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)
    is_pg = dialect == "postgresql"

    if not _table_exists(insp, "users", schema):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("password_hash", sa.String(length=512), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true") if is_pg else sa.text("1"),
            ),
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
            sa.UniqueConstraint("email", name="uq_users_email"),
            schema=schema,
        )

    # Helpful lookup index — safe if created twice due to name guard.
    idxs = _idxnames(insp, "users", schema)
    if "ix_users_email" not in idxs:
        op.create_index("ix_users_email", "users", ["email"], unique=False, schema=schema)


def downgrade() -> None:
    """
    Drop objects created by this migration (guarded).
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    if _table_exists(insp, "users", schema):
        idxs = _idxnames(insp, "users", schema)
        if "ix_users_email" in idxs:
            op.drop_index("ix_users_email", table_name="users", schema=schema)
        # Drop the table last
        try:
            op.drop_table("users", schema=schema)
        except Exception:
            # If other migrations added FKs to users, those must be dropped first in their downgrades.
            raise
