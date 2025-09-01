"""One-time import from public.companies into app.companies (if empty)

Revision ID: a202509010002
Revises: a202509010001
Create Date: 2025-09-01

This is safe and idempotent:
- Runs only if public.companies exists AND app.companies is empty
- Maps basic fields (name, website) and assigns tenant_id to the default tenant
- Generates synthetic company_number values to satisfy NOT NULL + uniqueness
"""

from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "a202509010002"
down_revision = "a202509010001"
branch_labels = None
depends_on = None


def _schema() -> str:
    return (os.getenv("ALEMBIC_SCHEMA") or os.getenv("POSTGRES_SCHEMA") or os.getenv("DB_SCHEMA") or "app").strip() or "app"


def upgrade():
    schema = _schema()
    conn = op.get_bind()

    has_public_companies = conn.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = 'public' AND table_name = 'companies'
            )
            """
        )
    ).scalar()

    if not has_public_companies:
        return

    has_app_companies = conn.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = :schema AND table_name = 'companies'
            )
            """
        ),
        {"schema": schema},
    ).scalar()
    if not has_app_companies:
        return

    app_count = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."companies"')).scalar_one()
    if app_count and app_count > 0:
        return

    default_tenant_id = conn.execute(
        text(f'SELECT id FROM "{schema}"."tenants" WHERE tenant_key = :k'),
        {"k": "default"},
    ).scalar()
    if default_tenant_id is None:
        conn.execute(
            text(f'INSERT INTO "{schema}"."tenants"(tenant_key, name) VALUES (\'default\', \'Default Tenant\') ON CONFLICT (tenant_key) DO NOTHING')
        )
        default_tenant_id = conn.execute(
            text(f'SELECT id FROM "{schema}"."tenants" WHERE tenant_key = :k'),
            {"k": "default"},
        ).scalar_one()

    conn.execute(
        text(
            f"""
            WITH src AS (
              SELECT
                name,
                website,
                ROW_NUMBER() OVER (ORDER BY name NULLS LAST, website NULLS LAST) AS rn
              FROM public.companies
            )
            INSERT INTO "{schema}"."companies"
              (tenant_id, company_number, name, website)
            SELECT
              :tid AS tenant_id,
              'TEMP-' || LPAD(rn::text, 8, '0') AS company_number,
              COALESCE(name, 'Unknown Company') AS name,
              website
            FROM src
            """
        ),
        {"tid": default_tenant_id},
    )


def downgrade():
    pass
