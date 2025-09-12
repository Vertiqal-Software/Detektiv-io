# alembic/versions/0002_users_role_member_and_indexes.py
"""bootstrap users table + simple roles/membership tables and helpful indexes

Revision ID: 0002_users_role_member_and_indexes
Revises: 0001_initial_users
Create Date: 2025-09-01 00:00:00.000000

This file was updated add-only to re-chain after restoring 0001 and to avoid
conflicts if the `users` table already exists. Source basis: uploaded file.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Set

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector

# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0002_users_role_member_and_indexes"
down_revision: Optional[str] = (
    "0001_initial_users"  # <-- re-chained to the restored root
)
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
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


def _column_exists(inspector: Inspector, table: str, column: str, schema: str) -> bool:
    try:
        cols = inspector.get_columns(table, schema=schema)
    except TypeError:
        cols = inspector.get_columns(table)
    for c in cols or []:
        if c.get("name") == column:
            return True
    return False


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def upgrade() -> None:
    """
    Create the initial `users` table (if it doesn't already exist from 0001),
    plus minimal `roles` and `user_roles` tables, and helpful indexes.

    Add-only recovery tweaks:
      • If `users` already exists from 0001, add `email_normalized` if missing.
      • Use Integer ids for roles/user_roles to match 0001.users.id type.
      • Guard all creates with existence checks to keep this migration idempotent.
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)
    is_pg = dialect == "postgresql"

    # -------------------- users --------------------
    users_exists = _table_exists(insp, "users", schema)
    if not users_exists:
        op.create_table(
            "users",
            # 0001 used Integer; we keep Integer here so subsequent FKs match even when we create fresh.
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            # Keep email_normalized now so later migrations can add a CI-unique on it
            sa.Column("email_normalized", sa.String(length=320), nullable=True),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("password_hash", sa.String(length=512), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true" if is_pg else "1"),
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
            schema=schema,
        )
    else:
        # If 0001 created users already, ensure email_normalized exists (needed by 0003).
        if not _column_exists(insp, "users", "email_normalized", schema):
            op.add_column(
                "users",
                sa.Column("email_normalized", sa.String(length=320), nullable=True),
                schema=schema,
            )

    # Helpful indexes (create if missing)
    idxs = _idxnames(insp, "users", schema)
    if "ix_users_email" not in idxs:
        op.create_index(
            "ix_users_email", "users", ["email"], unique=False, schema=schema
        )
    if "ix_users_created_at" not in idxs:
        # Only create if column exists
        if _column_exists(insp, "users", "created_at", schema):
            op.create_index(
                "ix_users_created_at",
                "users",
                ["created_at"],
                unique=False,
                schema=schema,
            )
    if "ix_users_email_normalized" not in idxs and _column_exists(
        insp, "users", "email_normalized", schema
    ):
        op.create_index(
            "ix_users_email_normalized",
            "users",
            ["email_normalized"],
            unique=False,
            schema=schema,
        )

    # -------------------- roles --------------------
    if not _table_exists(insp, "roles", schema):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "name",
                sa.String(length=64),
                nullable=False,
                comment="Role name (e.g., admin, analyst, member)",
            ),
            sa.Column("description", sa.String(length=255), nullable=True),
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
        # Unique role names
        op.create_unique_constraint("uq_roles_name", "roles", ["name"], schema=schema)

        # Seed common roles (best-effort; PG ON CONFLICT, else try/catch duplicates)
        try:
            if is_pg:
                op.execute(
                    text(
                        f'INSERT INTO "{schema}"."roles"(name, description) VALUES '
                        "('member','Default member role'),"
                        "('analyst','Analyst role'),"
                        "('admin','Administrator role') "
                        "ON CONFLICT DO NOTHING"
                    )
                )
            else:
                for r, d in (
                    ("member", "Default member role"),
                    ("analyst", "Analyst role"),
                    ("admin", "Administrator role"),
                ):
                    try:
                        op.execute(
                            text(
                                f"INSERT INTO roles(name, description) VALUES (:n, :d)"
                            ),
                            {"n": r, "d": d},
                        )
                    except Exception:
                        pass
        except Exception:
            # Non-fatal
            pass

    # -------------------- user_roles (membership) --------------------
    if not _table_exists(insp, "user_roles", schema):
        # Build FK targets (schema-qualified for PG)
        users_fk = f"{schema}.users.id" if is_pg else "users.id"
        roles_fk = f"{schema}.roles.id" if is_pg else "roles.id"

        op.create_table(
            "user_roles",
            # Match users.id / roles.id types (Integer)
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()") if is_pg else None,
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], [users_fk], ondelete="CASCADE", name="fk_user_roles_user"
            ),
            sa.ForeignKeyConstraint(
                ["role_id"], [roles_fk], ondelete="CASCADE", name="fk_user_roles_role"
            ),
            sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
            schema=schema,
        )

        # Convenience indexes for membership lookups
        op.create_index(
            "ix_user_roles_user", "user_roles", ["user_id"], unique=False, schema=schema
        )
        op.create_index(
            "ix_user_roles_role", "user_roles", ["role_id"], unique=False, schema=schema
        )


def downgrade() -> None:
    """
    Drop membership, roles, and users indexes created here (but keep the `users`
    table itself if it originated in 0001). All operations are guarded so
    downgrades are safe even if some objects were created by 0001.
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()

    # user_roles
    if _table_exists(insp, "user_roles", schema):
        idxs = _idxnames(insp, "user_roles", schema)
        if "ix_user_roles_user" in idxs:
            op.drop_index("ix_user_roles_user", table_name="user_roles", schema=schema)
        if "ix_user_roles_role" in idxs:
            op.drop_index("ix_user_roles_role", table_name="user_roles", schema=schema)
        op.drop_table("user_roles", schema=schema)

    # roles
    if _table_exists(insp, "roles", schema):
        # Unique constraint name guard
        idxs = _idxnames(insp, "roles", schema)
        if "uq_roles_name" in idxs:
            op.drop_constraint("uq_roles_name", "roles", type_="unique", schema=schema)
        op.drop_table("roles", schema=schema)

    # users (only drop indexes that this migration created)
    if _table_exists(insp, "users", schema):
        idxs = _idxnames(insp, "users", schema)
        if "ix_users_email_normalized" in idxs:
            op.drop_index(
                "ix_users_email_normalized", table_name="users", schema=schema
            )
        if "ix_users_created_at" in idxs:
            op.drop_index("ix_users_created_at", table_name="users", schema=schema)
        # DO NOT drop the `users` table here (it belongs to 0001 in a restored chain)
        # If this migration created `users` from scratch (only in rare recovery flows),
        # the prior migration wasn't applied; downgrading this revision shouldn't remove it.
