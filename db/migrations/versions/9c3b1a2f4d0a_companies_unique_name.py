# db/migrations/versions/9c3b1a2f4d0a_companies_unique_name.py
"""add unique index on companies.name

Revision ID: 9c3b1a2f4d0a
Revises: c5b2a3f9d8e1
Create Date: 2025-08-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9c3b1a2f4d0a"  # pragma: allowlist secret
down_revision = "c5b2a3f9d8e1"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ux_companies_name",
        "companies",
        ["name"],
        unique=True,
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("ux_companies_name", table_name="companies")
