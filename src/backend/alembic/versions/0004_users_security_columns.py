# alembic/versions/0004_users_security_columns.py
"""add security/account columns to users and helpful indexes/constraints

Revision ID: 0004_users_security_columns
Revises: 0003_users_email_ci_unique
Create Date: 2025-09-01 00:00:00.000000
"""

from __future__ import annotations

import os
import re
from typing import Set

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector

# --- Alembic identifiers ---
revision = "0004_users_security_columns"
down_revision = "0003_users_email_ci_unique"
branch_labels = None
depends_on = None


# --------------------------- helpers ---------------------------

def _get_schema() -> str:
    """
    Resolve the target schema from environment with a safe default.

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


def _colnames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    try:
        cols = inspector.get_columns(table, schema=schema)
    except TypeError:
        cols = inspector.get_columns(table)
    return {c["name"] for c in cols}


def _idxnames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    try:
        idxs = inspector.get_indexes(table, schema=schema)
    except TypeError:
        idxs = inspector.get_indexes(table)
    return {i["name"] for i in idxs}


def _ucnames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    names: Set[str] = set()
    try:
        ucs = inspector.get_unique_constraints(table, schema=schema)
    except TypeError:
        ucs = inspector.get_unique_constraints(table)
    for uc in ucs or []:
        n = uc.get("name")
        if n:
            names.add(n)
    return names


def _cknames(inspector: Inspector, table: str, schema: str) -> Set[str]:
    names: Set[str] = set()
    try:
        cks = inspector.get_check_constraints(table, schema=schema)
    except Exception:
        cks = []
    for ck in cks or []:
        n = ck.get("name")
        if n:
            names.add(n)
    return names


def _table_exists(inspector: Inspector, table: str, schema: str) -> bool:
    try:
        return table in inspector.get_table_names(schema=schema)
    except TypeError:
        return table in inspector.get_table_names()


def _qualified(table: str, schema: str, dialect: str) -> str:
    return f"{schema}.{table}" if dialect == "postgresql" else table


# --------------------------- migration ---------------------------

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
      - tenant_id BIGINT NULL   (FK is added later in 0008 to avoid anonymous FKs here)

    Also add helpful indexes/constraints if missing:
      - ix_users_tenant_email (tenant_id, email)                 [non-unique]
      - uq_users_tenant_email_norm (tenant_id, email_normalized) [unique, only if column exists]
      - ck_users_failed_login_count_nonneg (failed_login_count >= 0)

    Added (add-only):
      - ix_users_last_login_at (last_login_at)
      - ix_users_lockout_until (lockout_until)
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)

    if not _table_exists(insp, "users", schema):
        # Nothing to do if users table does not exist
        return

    cols = _colnames(insp, "users", schema)
    idxs = _idxnames(insp, "users", schema)
    ucs = _ucnames(insp, "users", schema)
    cks = _cknames(insp, "users", schema)

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

    # IMPORTANT: Add tenant_id WITHOUT an inline FK here.
    # A named FK (fk_users_tenant) is created later in 0008 to avoid duplicates/anonymous FKs.
    if "tenant_id" not in cols:
        op.add_column(
            "users",
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            schema=schema,
        )

    # ---- Backfill sanity (ensure non-null counters/flags) ----
    users_tn = _qualified("users", schema, dialect)

    if "failed_login_count" in _colnames(insp, "users", schema):
        bind.execute(sa.text(f"UPDATE {users_tn} SET failed_login_count = 0 WHERE failed_login_count IS NULL"))
    if "token_version" in _colnames(insp, "users", schema):
        bind.execute(sa.text(f"UPDATE {users_tn} SET token_version = 0 WHERE token_version IS NULL"))
    if "is_active" in _colnames(insp, "users", schema):
        bind.execute(sa.text(f"UPDATE {users_tn} SET is_active = TRUE WHERE is_active IS NULL"))

    # ---- Indexes / Constraints (create if missing) ----
    if "ix_users_tenant_email" not in idxs:
        op.create_index(
            "ix_users_tenant_email",
            "users",
            ["tenant_id", "email"],
            unique=False,
            schema=schema,
        )

    # Added: last_login_at index (if column exists)
    if "ix_users_last_login_at" not in idxs and "last_login_at" in _colnames(insp, "users", schema):
        op.create_index(
            "ix_users_last_login_at",
            "users",
            ["last_login_at"],
            unique=False,
            schema=schema,
        )

    # Added: lockout_until index (if column exists)
    if "ix_users_lockout_until" not in idxs and "lockout_until" in _colnames(insp, "users", schema):
        op.create_index(
            "ix_users_lockout_until",
            "users",
            ["lockout_until"],
            unique=False,
            schema=schema,
        )

    # Unique constraint on (tenant_id, email_normalized) ONLY if that column exists already.
    # (Typically created in 0008; this line will be a no-op here, which is fine.)
    if "email_normalized" in _colnames(insp, "users", schema):
        if "uq_users_tenant_email_norm" not in ucs:
            op.create_unique_constraint(
                "uq_users_tenant_email_norm",
                "users",
                ["tenant_id", "email_normalized"],
                schema=schema,
            )

    # Check constraint for non-negative failed_login_count (Postgres only to avoid SQLite pain)
    if "ck_users_failed_login_count_nonneg" not in cks and _dialect(bind) == "postgresql":
        op.create_check_constraint(
            "ck_users_failed_login_count_nonneg",
            "users",
            "failed_login_count >= 0",
            schema=schema,
        )


def downgrade() -> None:
    """
    Drop the indexes and columns introduced by this migration, but only if present.
    (Conditional drops keep downgrade idempotent if the schema was partially present.)
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    # Indexes
    idxs = _idxnames(insp, "users", schema)
    if "ix_users_tenant_email" in idxs:
        op.drop_index("ix_users_tenant_email", table_name="users", schema=schema)
    if "ix_users_last_login_at" in idxs:
        op.drop_index("ix_users_last_login_at", table_name="users", schema=schema)
    if "ix_users_lockout_until" in idxs:
        op.drop_index("ix_users_lockout_until", table_name="users", schema=schema)

    # Unique constraint
    ucs = _ucnames(insp, "users", schema)
    if "uq_users_tenant_email_norm" in ucs:
        op.drop_constraint("uq_users_tenant_email_norm", "users", type_="unique", schema=schema)

    # Check constraint
    cks = _cknames(insp, "users", schema)
    if "ck_users_failed_login_count_nonneg" in cks:
        op.drop_constraint("ck_users_failed_login_count_nonneg", "users", type_="check", schema=schema)

    # Columns (drop if present)
    cols = _colnames(insp, "users", schema)

    # Drop tenant_id first to avoid FK dependency issues (if any were added later)
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
