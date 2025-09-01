# alembic/versions/0003_users_email_ci_unique.py
"""enforce case-insensitive uniqueness on users.email

Revision ID: 0003_users_email_ci_unique
Revises: 0002_users_role_member_and_indexes
Create Date: 2025-09-01 00:00:00.000000
"""
from __future__ import annotations

import os
import re

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "0003_users_email_ci_unique"
down_revision = "0002_users_role_member_and_indexes"
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


def upgrade() -> None:
    """
    Steps:
      1) Normalize existing emails to lower(trim(email)) to prevent false conflicts.
      2) Verify there are no case-insensitive duplicates; if found, abort with a helpful error.
      3) Create a UNIQUE index on lower(email) to enforce CI uniqueness going forward.

    Notes:
      - We intentionally KEEP the existing case-sensitive UNIQUE constraint on email
        (usually named 'uq_users_email') for safety. The new functional unique index
        enforces the stronger case-insensitive rule.
    """
    bind = op.get_bind()
    schema = _get_schema()

    # 1) Normalize emails in place (lower + trim)
    bind.execute(
        sa.text(
            f"UPDATE {schema}.users SET email = LOWER(TRIM(email)) WHERE email IS NOT NULL"
        )
    )

    # 2) Guard: detect CI duplicates before creating the unique index
    dup_sql = sa.text(
        f"""
        SELECT lower(trim(email)) AS norm_email, COUNT(*) AS cnt
        FROM {schema}.users
        WHERE email IS NOT NULL
        GROUP BY lower(trim(email))
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC, norm_email ASC
        LIMIT 5
        """
    )
    dups = list(bind.execute(dup_sql).fetchall())
    if dups:
        # Show up to 5 offending normalized emails to help remediation
        example_list = ", ".join(f"{row[0]} (x{row[1]})" for row in dups)
        raise RuntimeError(
            "Cannot enforce case-insensitive unique emails: duplicates exist "
            f"(examples: {example_list}). Please merge or remove duplicates and re-run."
        )

    # 3) Create UNIQUE index on lower(email)
    #    Using Alembic's create_index with a functional expression via sa.text(...)
    op.create_index(
        "uq_users_email_lower_idx",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        schema=schema,
    )


def downgrade() -> None:
    """
    Drop the functional unique index on lower(email).
    We intentionally do NOT try to reverse-normalize email casing.
    """
    schema = _get_schema()
    op.drop_index(
        "uq_users_email_lower_idx",
        table_name="users",
        schema=schema,
    )
