# db/migrations/versions/20250901_0007_add_auth_fields_to_users.py
"""Add auth fields to users: role, failed_login_count, lockout_until, token_version

Revision ID: 20250901_0007
Revises: 20250901_0006
Create Date: 2025-09-01 00:07:00

Notes:
- Adds columns needed for production-grade auth (RBAC, lockouts, token revocation).
- Safe defaults for existing rows.
- Idempotent-ish: only adds columns/constraints if missing, in line with your style.
"""

from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# Alembic identifiers
revision: str = "20250901_0007"
down_revision: str | None = "20250901_0006"
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


def _check_constraints(conn, schema: str, table: str) -> set[str]:
    try:
        return {ck.get("name") for ck in _insp(conn).get_check_constraints(table, schema=schema)}
    except Exception:
        return set()


def upgrade() -> None:
    schema = _schema()
    conn = op.get_bind()

    # Ensure users table exists (it should, from 0004) :contentReference[oaicite:2]{index=2}.
    if not _has_table(conn, schema, "users"):
        # Nothing to do if table is missing (keeps migration safe on odd states).
        return

    # Add columns if they don't exist. Defaults are server-side for portability.
    if not _has_column(conn, schema, "users", "role"):
        op.add_column(
            "users",
            sa.Column(
                "role",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'analyst'"),
            ),
            schema=schema,
        )

    if not _has_column(conn, schema, "users", "failed_login_count"):
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

    if not _has_column(conn, schema, "users", "lockout_until"):
        op.add_column(
            "users",
            sa.Column(
                "lockout_until",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            schema=schema,
        )

    if not _has_column(conn, schema, "users", "token_version"):
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

    # Create role check constraint if missing
    existing_cks = _check_constraints(conn, schema, "users")
    if "ck_users_role" not in existing_cks:
        try:
            op.create_check_constraint(
                "ck_users_role",
                "users",
                "role IN ('admin','analyst')",
                schema=schema,
            )
        except Exception:
            # Keep forward-only progress even if some backends are picky.
            pass

    # Optional: if you want to remove server_defaults after backfilling, uncomment:
    # with op.batch_alter_table("users", schema=schema) as batch_op:
    #     batch_op.alter_column("role", server_default=None, existing_type=sa.String(length=32), nullable=False)
    #     batch_op.alter_column("failed_login_count", server_default=None, existing_type=sa.Integer(), nullable=False)
    #     batch_op.alter_column("token_version", server_default=None, existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    schema = _schema()
    # Drop constraint then columns in reverse order (defensive try/except to avoid hard-fails).
    try:
        op.drop_constraint("ck_users_role", "users", type_="check", schema=schema)
    except Exception:
        pass
    for col in ("token_version", "lockout_until", "failed_login_count", "role"):
        try:
            op.drop_column("users", col, schema=schema)
        except Exception:
            pass
