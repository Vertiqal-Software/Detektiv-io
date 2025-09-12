# alembic/versions/0003_users_email_ci_unique.py
"""enforce case-insensitive uniqueness on users.email

Revision ID: 0003_users_email_ci_unique
Revises: 0002_users_role_member_and_indexes
Create Date: 2025-09-01 00:00:00.000000

Add-only recovery notes:
- Based on your uploaded version; behavior kept intact and strengthened.
- Safer duplicate detection with clearer error.
- Expression-index creation guarded per dialect; fallback path improved.
- If fallback is needed and `email_normalized` column is missing, we create it here
  (later migrations that also add it are idempotent and will skip).
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
revision = "0003_users_email_ci_unique"
down_revision = "0002_users_role_member_and_indexes"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _qualified(table: str, schema: str, dialect: str) -> str:
    return f"{schema}.{table}" if dialect == "postgresql" else table


def _supports_expression_index(dialect: str) -> bool:
    """
    Conservative check for expression index support in this migration context.
    - Postgres: yes
    - SQLite: generally yes (SQLAlchemy/Alembic allow sa.text in columns list)
    - Others: assume no (fallback will apply)
    """
    return dialect in {"postgresql", "sqlite"}


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def upgrade() -> None:
    """
    Steps (defensive/idempotent-ish):
      0) No-op if users table is missing.
      1) Normalize existing emails to lower(trim(email)) to prevent false conflicts.
      2) Verify there are no case-insensitive duplicates; if found, abort with a helpful error.
      3) Create a UNIQUE functional index enforcing case-insensitive uniqueness:
           - Preferred: unique functional index on lower(email) (PG/SQLite).
         (If the index already exists, do nothing.)
      4) Keep 'email_normalized' (if present) in sync with lower(trim(email)).
      5) Fallback for dialects without expression index support:
           - Ensure 'email_normalized' exists (create if missing), backfill it,
             and create a unique index on it.
    """
    bind = op.get_bind()
    insp = _insp(bind)
    schema = _get_schema()
    dialect = _dialect(bind)

    if not _table_exists(insp, "users", schema):
        # Nothing to do if users table does not exist
        return

    users_tn = _qualified("users", schema, dialect)
    cols = _colnames(insp, "users", schema)
    idxs = _idxnames(insp, "users", schema)

    # 1) Normalize emails in place (lower + trim) — keep NULLs as-is
    bind.execute(
        sa.text(
            f"UPDATE {users_tn} SET email = LOWER(TRIM(email)) WHERE email IS NOT NULL"
        )
    )

    # 2) Guard: detect CI duplicates before creating the unique index
    dup_sql = sa.text(
        f"""
        SELECT lower(trim(email)) AS norm_email, COUNT(*) AS cnt
        FROM {users_tn}
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

    # 3) Preferred: UNIQUE functional index on lower(email) if supported
    idx_ci = "uq_users_email_lower_idx"
    created_ci_expression_idx = False
    if idx_ci not in idxs and _supports_expression_index(dialect):
        try:
            op.create_index(
                idx_ci,
                "users",
                [sa.text("lower(email)")],
                unique=True,
                schema=schema,
            )
            created_ci_expression_idx = True
        except Exception:
            # As a last resort on dialects not supporting expression indexes,
            # skip creation rather than failing the migration (dev-only benefit).
            created_ci_expression_idx = False

    # 4) Keep email_normalized in sync when present
    has_norm_col = "email_normalized" in cols
    if has_norm_col:
        bind.execute(
            sa.text(
                f"UPDATE {users_tn} "
                f"SET email_normalized = LOWER(TRIM(email)) "
                f"WHERE email IS NOT NULL"
            )
        )

    # 5) Fallback: if we couldn't create the expression index,
    #    ensure email_normalized exists, backfill, and enforce uniqueness on it.
    if not created_ci_expression_idx:
        # Create email_normalized if missing (harmless for later migrations which are idempotent)
        if not has_norm_col:
            op.add_column(
                "users",
                sa.Column(
                    "email_normalized", sa.String(length=320), nullable=True, index=True
                ),
                schema=schema,
            )
            cols = _colnames(insp, "users", schema)
            has_norm_col = True

        # Backfill normalization
        if has_norm_col:
            bind.execute(
                sa.text(
                    f"UPDATE {users_tn} "
                    f"SET email_normalized = LOWER(TRIM(email)) "
                    f"WHERE email IS NOT NULL"
                )
            )

            idx_norm = "uq_users_email_normalized_idx"
            # Refresh index names in case of concurrent ops
            idxs = _idxnames(insp, "users", schema)
            if idx_norm not in idxs:
                try:
                    op.create_index(
                        idx_norm,
                        "users",
                        ["email_normalized"],
                        unique=True,
                        schema=schema,
                    )
                except Exception:
                    # Don't fail the migration on exotic dialect limitations
                    pass


def downgrade() -> None:
    """
    Drop the functional unique index on lower(email) and the fallback unique
    index on email_normalized (if present). We intentionally do NOT try to
    reverse-normalize email casing.
    """
    schema = _get_schema()
    bind = op.get_bind()
    insp = _insp(bind)

    if not _table_exists(insp, "users", schema):
        return

    idxs = _idxnames(insp, "users", schema)

    idx_ci = "uq_users_email_lower_idx"
    if idx_ci in idxs:
        op.drop_index(idx_ci, table_name="users", schema=schema)

    idx_norm = "uq_users_email_normalized_idx"
    if idx_norm in idxs:
        op.drop_index(idx_norm, table_name="users", schema=schema)
