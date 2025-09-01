# alembic/versions/0002_users_role_member_and_indexes.py
"""broaden users.role and add helpful indexes

Revision ID: 0002_users_role_member_and_indexes
Revises: 0001_initial
Create Date: 2025-09-01 00:00:00.000000
"""
from __future__ import annotations

import os
import re

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "0002_users_role_member_and_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _get_schema() -> str:
    """
    Resolve the target schema from environment with a safe default.
    Mirrors logic from 0001_initial to ensure objects land in the same schema.

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


def upgrade() -> None:
    schema = _get_schema()

    # 1) Broaden role constraint to include 'member'
    #    Old: role IN ('admin','analyst')
    #    New: role IN ('admin','analyst','member')
    op.drop_constraint(
        "ck_users_role",
        "users",
        type_="check",
        schema=schema,
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','analyst','member')",
        schema=schema,
    )

    # 2) Helpful composite index for common listings/filters
    #    Speeds admin user list and role/status dashboards
    op.create_index(
        "ix_users_active_role",
        "users",
        ["is_active", "role"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = _get_schema()

    # Drop the index we added
    op.drop_index(
        "ix_users_active_role",
        table_name="users",
        schema=schema,
    )

    # Revert the role constraint to its original form
    op.drop_constraint(
        "ck_users_role",
        "users",
        type_="check",
        schema=schema,
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','analyst')",
        schema=schema,
    )
