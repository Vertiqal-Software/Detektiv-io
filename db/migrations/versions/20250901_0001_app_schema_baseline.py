"""Baseline: app schema, tenants, users, companies (full), source_events.

Revision ID: a202509010001
Revises: None
Create Date: 2025-09-01

This baseline is idempotent:
- Creates the application schema (default: "app") if missing
- Creates/ensures tenants, users, companies, source_events with correct columns + constraints
- Inserts a default tenant ('default') if missing
- Enforces per-tenant uniqueness on company_number and NOT NULL for company_number
"""

from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# Alembic identifiers
revision = "a202509010001"
down_revision = None
branch_labels = None
depends_on = None


def _schema() -> str:
    return (os.getenv("ALEMBIC_SCHEMA") or os.getenv("POSTGRES_SCHEMA") or os.getenv("DB_SCHEMA") or "app").strip() or "app"


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


def _unique_cols(conn, schema: str, table: str) -> set[tuple[str, ...]]:
    try:
        return {tuple(uc.get("column_names") or ()) for uc in _insp(conn).get_unique_constraints(table, schema=schema)}
    except Exception:
        return set()


def upgrade():
    schema = _schema()
    conn = op.get_bind()

    # Ensure app schema exists (env.py also sets search_path)
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # ---------- tenants ----------
    if not _has_table(conn, schema, "tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_key", sa.String(length=64), nullable=False, unique=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema=schema,
        )

    # Upsert default tenant
    conn.execute(
        text(f'INSERT INTO "{schema}"."tenants"(tenant_key, name) VALUES (:k,:n) ON CONFLICT (tenant_key) DO NOTHING'),
        {"k": "default", "n": "Default Tenant"},
    )
    default_tenant_id = conn.execute(
        text(f'SELECT id FROM "{schema}"."tenants" WHERE tenant_key = :k'),
        {"k": "default"},
    ).scalar_one()

    # ---------- users ----------
    if not _has_table(conn, schema, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema=schema,
        )

    # ---------- companies ----------
    if not _has_table(conn, schema, "companies"):
        op.create_table(
            "companies",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("company_number", sa.String(length=16), nullable=False),
            sa.Column("name", sa.String(length=300), nullable=False),
            sa.Column("website", sa.String(length=255)),
            sa.Column("status", sa.String(length=50)),
            sa.Column("incorporated_on", sa.Date()),
            sa.Column("jurisdiction", sa.String(length=50)),
            sa.Column("last_accounts", sa.JSON()),
            sa.Column("companies_house_number", sa.String(length=20)),
            sa.Column("companies_house_status", sa.String(length=50)),
            sa.Column("email", sa.String(length=255)),
            sa.Column("phone", sa.String(length=50)),
            sa.Column("address_line1", sa.Text()),
            sa.Column("address_line2", sa.Text()),
            sa.Column("city", sa.String(length=100)),
            sa.Column("county", sa.String(length=100)),
            sa.Column("postcode", sa.String(length=20)),
            sa.Column("country", sa.String(length=10), nullable=False, server_default="GB"),
            sa.Column("industry", sa.String(length=100)),
            sa.Column("sic_code", sa.String(length=10)),
            sa.Column("employee_count", sa.Integer()),
            sa.Column("annual_revenue", sa.Integer()),
            sa.Column("data_source", sa.String(length=50), nullable=False, server_default="manual"),
            sa.Column("last_updated_from_source", sa.DateTime(timezone=True)),
            sa.Column("is_prospect", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("prospect_stage", sa.String(length=50)),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("tenant_id", "company_number", name="uq_companies_tenant_company_number"),
            schema=schema,
        )

        op.create_foreign_key(
            "fk_companies_tenant_id",
            "companies",
            "tenants",
            ["tenant_id"],
            ["id"],
            source_schema=schema,
            referent_schema=schema,
        )
        op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"], schema=schema)
        op.create_index("ix_companies_company_number", "companies", ["company_number"], schema=schema)
        op.create_index("ix_companies_name", "companies", ["name"], schema=schema)

    else:
        # Bring an existing companies up to spec idempotently
        to_add: list[sa.Column] = []

        required = {
            "tenant_id": sa.Integer(),
            "company_number": sa.String(length=16),
            "name": sa.String(length=300),
        }
        for col_name, col_type in required.items():
            if not _has_column(conn, schema, "companies", col_name):
                to_add.append(sa.Column(col_name, col_type, nullable=True))

        optional_cols = {
            "website": sa.String(length=255),
            "status": sa.String(length=50),
            "incorporated_on": sa.Date(),
            "jurisdiction": sa.String(length=50),
            "last_accounts": sa.JSON(),
            "companies_house_number": sa.String(length=20),
            "companies_house_status": sa.String(length=50),
            "email": sa.String(length=255),
            "phone": sa.String(length=50),
            "address_line1": sa.Text(),
            "address_line2": sa.Text(),
            "city": sa.String(length=100),
            "county": sa.String(length=100),
            "postcode": sa.String(length=20),
            "country": sa.String(length=10),
            "industry": sa.String(length=100),
            "sic_code": sa.String(length=10),
            "employee_count": sa.Integer(),
            "annual_revenue": sa.Integer(),
            "data_source": sa.String(length=50),
            "last_updated_from_source": sa.DateTime(timezone=True),
            "is_prospect": sa.Boolean(),
            "prospect_stage": sa.String(length=50),
            "notes": sa.Text(),
            "created_at": sa.DateTime(timezone=True),
            "updated_at": sa.DateTime(timezone=True),
        }
        for col_name, col_type in optional_cols.items():
            if not _has_column(conn, schema, "companies", col_name):
                to_add.append(sa.Column(col_name, col_type, nullable=True))

        if to_add:
            op.add_column("companies", to_add.pop(0), schema=schema)
            for c in to_add:
                op.add_column("companies", c, schema=schema)

        # Backfills
        if _has_column(conn, schema, "companies", "tenant_id"):
            conn.execute(text(f'UPDATE "{schema}"."companies" SET tenant_id = :tid WHERE tenant_id IS NULL'),
                         {"tid": default_tenant_id})
        if _has_column(conn, schema, "companies", "company_number"):
            conn.execute(
                text(
                    f'UPDATE "{schema}"."companies" '
                    f"SET company_number = CONCAT('TEMP-', id::text) "
                    f"WHERE company_number IS NULL"
                )
            )

        # Unique constraint
        uqs = _unique_cols(conn, schema, "companies")
        if ("tenant_id", "company_number") not in uqs and ("company_number", "tenant_id") not in uqs:
            try:
                op.create_unique_constraint("uq_companies_tenant_company_number", "companies",
                                            ["tenant_id", "company_number"], schema=schema)
            except Exception:
                pass

        # Tighten NOT NULLs
        if _has_column(conn, schema, "companies", "tenant_id"):
            op.alter_column("companies", "tenant_id", nullable=False, schema=schema, existing_type=sa.Integer())
        if _has_column(conn, schema, "companies", "company_number"):
            op.alter_column("companies", "company_number", nullable=False, schema=schema,
                            existing_type=sa.String(length=16))
        if _has_column(conn, schema, "companies", "name"):
            op.alter_column("companies", "name", nullable=False, schema=schema, existing_type=sa.String(length=300))

        # Indexes
        idxs = _index_names(conn, schema, "companies")
        if "ix_companies_tenant_id" not in idxs and _has_column(conn, schema, "companies", "tenant_id"):
            op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"], schema=schema)
        if "ix_companies_company_number" not in idxs and _has_column(conn, schema, "companies", "company_number"):
            op.create_index("ix_companies_company_number", "companies", ["company_number"], schema=schema)
        if "ix_companies_name" not in idxs and _has_column(conn, schema, "companies", "name"):
            op.create_index("ix_companies_name", "companies", ["name"], schema=schema)

    # ---------- source_events ----------
    if not _has_table(conn, schema, "source_events"):
        op.create_table(
            "source_events",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("company_id", sa.Integer, nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.JSON()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema=schema,
        )
        op.create_foreign_key("fk_source_events_tenant", "source_events", "tenants",
                              ["tenant_id"], ["id"], source_schema=schema, referent_schema=schema)
        op.create_foreign_key("fk_source_events_company", "source_events", "companies",
                              ["company_id"], ["id"], source_schema=schema, referent_schema=schema)
        op.create_index("ix_source_events_tenant_id", "source_events", ["tenant_id"], schema=schema)
        op.create_index("ix_source_events_company_id", "source_events", ["company_id"], schema=schema)


def downgrade():
    schema = _schema()
    try:
        op.drop_index("ix_source_events_company_id", table_name="source_events", schema=schema)
        op.drop_index("ix_source_events_tenant_id", table_name="source_events", schema=schema)
        op.drop_constraint("fk_source_events_company", "source_events", type_="foreignkey", schema=schema)
        op.drop_constraint("fk_source_events_tenant", "source_events", type_="foreignkey", schema=schema)
        op.drop_table("source_events", schema=schema)
    except Exception:
        pass
    # Do not drop companies/users/tenants in downgrade (avoid data loss).
    pass
