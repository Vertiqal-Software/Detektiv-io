"""create companies table

Revision ID: c5b2a3f9d8e1
Revises: 8f8e34e223b0
Create Date: 2025-08-26

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c5b2a3f9d8e1"  # pragma: allowlist secret
down_revision = "8f8e34e223b0"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_companies_name", "companies", ["name"])


def downgrade() -> None:
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
