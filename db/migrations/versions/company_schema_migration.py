"""enhance companies table with full schema

Revision ID: e1f2a3b4c5d6
Revises: a2f9e70c0e4a  
Create Date: 2025-08-28

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a2f9e70c0e4a"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None  # pragma: allowlist secret


def upgrade() -> None:
    """Add comprehensive fields to companies table."""

    # Add new columns to existing companies table
    # Companies House information
    op.add_column(
        "companies",
        sa.Column("companies_house_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("companies_house_status", sa.String(length=50), nullable=True),
    )

    # Contact information
    op.add_column("companies", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("phone", sa.String(length=50), nullable=True))

    # Address information
    op.add_column("companies", sa.Column("address_line1", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("address_line2", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column(
        "companies", sa.Column("county", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("postcode", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("country", sa.String(length=10), nullable=False, server_default="GB"),
    )

    # Business classification
    op.add_column(
        "companies", sa.Column("industry", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("sic_code", sa.String(length=10), nullable=True)
    )
    op.add_column("companies", sa.Column("employee_count", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("annual_revenue", sa.Integer(), nullable=True))

    # Data source tracking
    op.add_column(
        "companies",
        sa.Column(
            "data_source", sa.String(length=50), nullable=False, server_default="manual"
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "last_updated_from_source", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # Sales intelligence metadata
    op.add_column(
        "companies",
        sa.Column("is_prospect", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "companies", sa.Column("prospect_stage", sa.String(length=50), nullable=True)
    )
    op.add_column("companies", sa.Column("notes", sa.Text(), nullable=True))

    # Add updated_at timestamp field
    op.add_column(
        "companies", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Create additional indexes
    op.create_index(
        "ix_companies_companies_house_number",
        "companies",
        ["companies_house_number"],
        unique=True,
    )
    op.create_index("ix_companies_postcode", "companies", ["postcode"])
    op.create_index("ix_companies_country", "companies", ["country"])
    op.create_index("ix_companies_industry", "companies", ["industry"])
    op.create_index("ix_companies_is_prospect", "companies", ["is_prospect"])
    op.create_index("ix_companies_data_source", "companies", ["data_source"])

    # Add check constraints for data validation
    op.create_check_constraint(
        "ck_companies_employee_count_positive",
        "companies",
        "employee_count IS NULL OR employee_count >= 0",
    )

    op.create_check_constraint(
        "ck_companies_annual_revenue_positive",
        "companies",
        "annual_revenue IS NULL OR annual_revenue >= 0",
    )

    op.create_check_constraint(
        "ck_companies_supported_countries",
        "companies",
        "country IN ('GB', 'IE', 'US', 'CA', 'AU', 'NZ')",
    )

    op.create_check_constraint(
        "ck_companies_valid_data_source",
        "companies",
        "data_source IN ('manual', 'companies_house', 'scraped', 'api', 'import')",
    )


def downgrade() -> None:
    """Remove enhanced fields from companies table."""

    # Drop check constraints
    op.drop_constraint("ck_companies_valid_data_source", "companies")
    op.drop_constraint("ck_companies_supported_countries", "companies")
    op.drop_constraint("ck_companies_annual_revenue_positive", "companies")
    op.drop_constraint("ck_companies_employee_count_positive", "companies")

    # Drop indexes
    op.drop_index("ix_companies_data_source", table_name="companies")
    op.drop_index("ix_companies_is_prospect", table_name="companies")
    op.drop_index("ix_companies_industry", table_name="companies")
    op.drop_index("ix_companies_country", table_name="companies")
    op.drop_index("ix_companies_postcode", table_name="companies")
    op.drop_index("ix_companies_companies_house_number", table_name="companies")

    # Drop columns (in reverse order of addition)
    op.drop_column("companies", "updated_at")
    op.drop_column("companies", "notes")
    op.drop_column("companies", "prospect_stage")
    op.drop_column("companies", "is_prospect")
    op.drop_column("companies", "last_updated_from_source")
    op.drop_column("companies", "data_source")
    op.drop_column("companies", "annual_revenue")
    op.drop_column("companies", "employee_count")
    op.drop_column("companies", "sic_code")
    op.drop_column("companies", "industry")
    op.drop_column("companies", "country")
    op.drop_column("companies", "postcode")
    op.drop_column("companies", "county")
    op.drop_column("companies", "city")
    op.drop_column("companies", "address_line2")
    op.drop_column("companies", "address_line1")
    op.drop_column("companies", "phone")
    op.drop_column("companies", "email")
    op.drop_column("companies", "companies_house_status")
    op.drop_column("companies", "companies_house_number")
