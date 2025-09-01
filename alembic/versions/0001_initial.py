"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-08-31 00:00:00.000000
"""
from __future__ import annotations

import os
import re

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _get_schema() -> str:
    """
    Resolve the target schema from environment with a safe default.
    Only allow [A-Za-z0-9_] and must start with letter/_ to avoid SQL injection.
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

    # Ensure schema exists (PostgreSQL)
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    # -------------------------------
    # tenants
    # -------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_key", name="uq_tenants_tenant_key"),
        schema=schema,
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=False, schema=schema)

    # -------------------------------
    # users
    # -------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'analyst'"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("lockout_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("email <> ''", name="ck_users_email_nonempty"),
        sa.CheckConstraint("role IN ('admin','analyst')", name="ck_users_role"),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_nonneg"),
        sa.CheckConstraint("token_version >= 0", name="ck_users_token_version_nonneg"),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{schema}.tenants.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        schema=schema,
    )
    op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"], unique=False, schema=schema)

    # -------------------------------
    # companies
    # -------------------------------
    op.create_table(
        "companies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address_line1", sa.Text(), nullable=True),
        sa.Column("address_line2", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("postcode", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=10), server_default=sa.text("'GB'"), nullable=False),
        sa.Column("company_number", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("incorporated_on", sa.Date(), nullable=True),
        sa.Column("jurisdiction", sa.String(length=50), nullable=True),
        sa.Column("last_accounts", sa.JSON(), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("sic_code", sa.String(length=10), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("annual_revenue", sa.Integer(), nullable=True),
        sa.Column("data_source", sa.String(length=50), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("last_updated_from_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_prospect", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("prospect_stage", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "employee_count IS NULL OR employee_count >= 0",
            name="ck_companies_employee_count_positive",
        ),
        sa.CheckConstraint(
            "annual_revenue IS NULL OR annual_revenue >= 0",
            name="ck_companies_annual_revenue_positive",
        ),
        sa.CheckConstraint(
            "country IS NULL OR country IN ('GB','IE','US','CA','AU','NZ')",
            name="ck_companies_supported_countries",
        ),
        sa.CheckConstraint(
            "data_source IN ('manual','companies_house','scraped','api','import')",
            name="ck_companies_valid_data_source",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{schema}.tenants.id"]),
        schema=schema,
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=False, schema=schema)
    op.create_index("ix_companies_tenant_name", "companies", ["tenant_id", "name"], unique=False, schema=schema)
    op.create_index("ix_companies_postcode", "companies", ["postcode"], unique=False, schema=schema)
    op.create_index("ix_companies_company_number", "companies", ["company_number"], unique=False, schema=schema)

    # -------------------------------
    # source_events
    # -------------------------------
    op.create_table(
        "source_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{schema}.tenants.id"]),
        sa.ForeignKeyConstraint(["company_id"], [f"{schema}.companies.id"]),
        schema=schema,
    )
    op.create_index("ix_source_events_company", "source_events", ["company_id"], unique=False, schema=schema)
    op.create_index(
        "ix_source_events_tenant_company", "source_events", ["tenant_id", "company_id"], unique=False, schema=schema
    )


def downgrade() -> None:
    schema = _get_schema()

    # Drop in reverse dependency order
    op.drop_index("ix_source_events_tenant_company", table_name="source_events", schema=schema)
    op.drop_index("ix_source_events_company", table_name="source_events", schema=schema)
    op.drop_table("source_events", schema=schema)

    op.drop_index("ix_companies_company_number", table_name="companies", schema=schema)
    op.drop_index("ix_companies_postcode", table_name="companies", schema=schema)
    op.drop_index("ix_companies_tenant_name", table_name="companies", schema=schema)
    op.drop_index("ix_companies_name", table_name="companies", schema=schema)
    op.drop_table("companies", schema=schema)

    op.drop_index("ix_users_tenant_email", table_name="users", schema=schema)
    op.drop_table("users", schema=schema)

    op.drop_index("ix_tenants_name", table_name="tenants", schema=schema)
    op.drop_table("tenants", schema=schema)

    # (Deliberately keep the schema; other objects may exist.)
