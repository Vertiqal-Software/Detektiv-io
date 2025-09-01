#!/usr/bin/env python3
"""
Detecktiv.io Management CLI

This script provides command-line management utilities for the Detecktiv.io application.
Run with --help to see available commands.

Usage:
    python manage.py <command> [options]

Examples:
    python manage.py db-init                    # Initialize database
    python manage.py db-seed                    # Seed with sample data
    python manage.py companies-house-sync       # Sync all companies with Companies House
    python manage.py export-companies           # Export companies to CSV
    python manage.py --help                     # Show all commands
"""

import asyncio
import csv
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

import click
from sqlalchemy.orm import Session

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.core.database import (
    get_db_session,
    check_database_connection,
    startup_database,
)
from app.core.logging import setup_logging, get_logger
from app.models.company import Company
from app.services.company_service import CompanyService
from app.services.companies_house_service import CompaniesHouseService
from app.schemas.company import CompanyCreate

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, verbose):
    """Detecktiv.io management CLI."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Store context
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
def check_config():
    """Check application configuration."""
    click.echo("🔧 Checking configuration...")

    # Database configuration
    click.echo(f"Database URL: {settings.get_database_url(mask_password=True)}")
    click.echo(
        f"Environment: {settings.is_development() and 'Development' or 'Production'}"
    )
    click.echo(f"Debug mode: {settings.debug}")
    click.echo(f"Log level: {settings.log_level}")

    # Companies House API
    if settings.companies_house_api_key:
        masked_key = (
            settings.companies_house_api_key[:8]
            + "..."
            + settings.companies_house_api_key[-4:]
        )
        click.echo(f"Companies House API key: {masked_key}")
    else:
        click.echo("⚠️  Companies House API key not configured")

    # CORS origins
    click.echo(f"CORS origins: {', '.join(settings.cors_origins)}")

    click.echo("✅ Configuration check complete")


@cli.command()
def check_db():
    """Check database connectivity and status."""
    click.echo("🔍 Checking database connection...")

    is_connected, message = check_database_connection()

    if is_connected:
        click.echo("✅ Database connection successful")

        # Get additional database info
        from app.core.database import get_database_info

        db_info = get_database_info()

        if db_info.get("connected"):
            click.echo(f"Database: {db_info['database_name']}")
            click.echo(f"PostgreSQL version: {db_info['postgresql_version']}")
            click.echo(f"Active connections: {db_info['active_connections']}")
    else:
        click.echo(f"❌ Database connection failed: {message}")
        sys.exit(1)


@cli.command()
def db_init():
    """Initialize database with latest migrations."""
    click.echo("🚀 Initializing database...")

    # Check if alembic is available
    try:
        import alembic
        from alembic import command
        from alembic.config import Config
    except ImportError:
        click.echo("❌ Alembic not installed. Run: pip install alembic")
        sys.exit(1)

    # Run migrations
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        click.echo("✅ Database initialized with latest migrations")
    except Exception as e:
        click.echo(f"❌ Migration failed: {e}")
        sys.exit(1)


@cli.command()
@click.option("--reset", is_flag=True, help="Reset existing data")
def db_seed(reset):
    """Seed database with sample data."""
    if reset:
        click.echo("🗑️  Resetting existing data...")

    click.echo("🌱 Seeding database with sample data...")

    try:
        with get_db_session() as session:
            service = CompanyService(session)

            if reset:
                # Clear existing companies (in development only)
                if settings.is_development():
                    session.query(Company).delete()
                    session.commit()
                    click.echo("Cleared existing company data")

            # Sample companies data
            sample_companies = [
                CompanyCreate(
                    name="Acme Technology Ltd",
                    website="https://acme-tech.co.uk",
                    email="info@acme-tech.co.uk",
                    phone="+44 20 7123 4567",
                    address_line1="123 Tech Street",
                    city="London",
                    postcode="EC2A 1AA",
                    country="GB",
                    industry="Technology",
                    employee_count=50,
                    annual_revenue=2500000,
                    is_prospect=True,
                    prospect_stage="qualified",
                ),
                CompanyCreate(
                    name="Global Software Solutions",
                    website="https://globalsoftware.com",
                    email="contact@globalsoftware.com",
                    phone="+44 161 234 5678",
                    address_line1="456 Innovation Drive",
                    city="Manchester",
                    postcode="M1 2BB",
                    country="GB",
                    industry="Software Development",
                    employee_count=120,
                    annual_revenue=8500000,
                ),
                CompanyCreate(
                    name="Digital Marketing Experts",
                    website="https://digitalexperts.co.uk",
                    email="hello@digitalexperts.co.uk",
                    phone="+44 117 345 6789",
                    address_line1="789 Creative Lane",
                    city="Bristol",
                    postcode="BS1 3CC",
                    country="GB",
                    industry="Digital Marketing",
                    employee_count=25,
                    annual_revenue=1200000,
                    is_prospect=True,
                    prospect_stage="lead",
                ),
                CompanyCreate(
                    name="Enterprise Systems Ltd",
                    website="https://enterprise-sys.com",
                    email="sales@enterprise-sys.com",
                    address_line1="321 Business Park",
                    city="Birmingham",
                    postcode="B2 4DD",
                    country="GB",
                    industry="Enterprise Software",
                    employee_count=200,
                    annual_revenue=15000000,
                    companies_house_number="09876543",
                ),
                CompanyCreate(
                    name="Cloud Infrastructure Co",
                    website="https://cloudinfra.io",
                    email="info@cloudinfra.io",
                    address_line1="100 Server Street",
                    city="Edinburgh",
                    postcode="EH1 1AA",
                    country="GB",
                    industry="Cloud Computing",
                    employee_count=75,
                    annual_revenue=4200000,
                ),
            ]

            created_count = 0
            for company_data in sample_companies:
                try:
                    # Check if company already exists
                    existing = service.get_company_by_name(company_data.name)
                    if existing:
                        if not reset:
                            click.echo(
                                f"Skipping existing company: {company_data.name}"
                            )
                            continue

                    company = service.create_company(company_data)
                    created_count += 1
                    click.echo(f"Created: {company.name}")

                except Exception as e:
                    click.echo(f"Failed to create {company_data.name}: {e}")

            click.echo(f"✅ Created {created_count} sample companies")

    except Exception as e:
        click.echo(f"❌ Seeding failed: {e}")
        sys.exit(1)


@cli.command()
@click.option("--limit", default=100, help="Maximum number of companies to sync")
@click.option("--force", is_flag=True, help="Force update even if recently synced")
def companies_house_sync(limit, force):
    """Sync companies with Companies House API."""
    if not settings.companies_house_api_key:
        click.echo("❌ Companies House API key not configured")
        sys.exit(1)

    click.echo(f"🏢 Syncing up to {limit} companies with Companies House...")

    async def sync_companies():
        success_count = 0
        error_count = 0

        async with CompaniesHouseService() as ch_service:
            with get_db_session() as session:
                service = CompanyService(session)

                # Get companies that have Companies House numbers
                companies = (
                    session.query(Company)
                    .filter(Company.companies_house_number.isnot(None))
                    .limit(limit)
                    .all()
                )

                if not companies:
                    click.echo("No companies found with Companies House numbers")
                    return

                click.echo(f"Found {len(companies)} companies to potentially sync")

                for company in companies:
                    try:
                        # Check if sync is needed
                        if not force and company.last_updated_from_source:
                            days_ago = (
                                datetime.utcnow() - company.last_updated_from_source
                            ).days
                            if days_ago < 7:  # Skip if updated within 7 days
                                continue

                        click.echo(
                            f"Syncing: {company.name} ({company.companies_house_number})"
                        )

                        success, message, updated_fields = (
                            await ch_service.update_company_from_companies_house(
                                service, company.id, force_update=force
                            )
                        )

                        if success:
                            success_count += 1
                            click.echo(f"  ✅ Updated {len(updated_fields)} fields")
                        else:
                            click.echo(f"  ⚠️  {message}")

                    except Exception as e:
                        error_count += 1
                        click.echo(f"  ❌ Error syncing {company.name}: {e}")

        click.echo(f"✅ Sync complete: {success_count} updated, {error_count} errors")

    # Run async function
    asyncio.run(sync_companies())


@cli.command()
@click.option("--output", "-o", default="companies_export.csv", help="Output CSV file")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "json"]),
    default="csv",
    help="Output format",
)
def export_companies(output, output_format):
    """Export companies to CSV or JSON."""
    click.echo(f"📄 Exporting companies to {output}...")

    try:
        with get_db_session() as session:
            companies = session.query(Company).all()

            if not companies:
                click.echo("No companies found to export")
                return

            output_path = Path(output)

            if output_format == "csv":
                with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                    # Define CSV columns
                    fieldnames = [
                        "id",
                        "name",
                        "website",
                        "email",
                        "phone",
                        "address_line1",
                        "address_line2",
                        "city",
                        "county",
                        "postcode",
                        "country",
                        "industry",
                        "sic_code",
                        "employee_count",
                        "annual_revenue",
                        "companies_house_number",
                        "companies_house_status",
                        "data_source",
                        "is_prospect",
                        "prospect_stage",
                        "created_at",
                        "updated_at",
                    ]

                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

                    for company in companies:
                        # Convert company to dict, handling datetime objects
                        company_dict = company.to_dict()

                        # Ensure all fieldnames are present
                        row = {
                            field: company_dict.get(field, "") for field in fieldnames
                        }

                        writer.writerow(row)

            elif output_format == "json":
                import json

                companies_data = [company.to_dict() for company in companies]

                with open(output_path, "w", encoding="utf-8") as jsonfile:
                    json.dump(companies_data, jsonfile, indent=2, default=str)

            click.echo(f"✅ Exported {len(companies)} companies to {output_path}")

    except Exception as e:
        click.echo(f"❌ Export failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument("csv_file", type=click.Path(exists=True))
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be imported without actually doing it",
)
def import_companies(csv_file, dry_run):
    """Import companies from CSV file."""
    click.echo(f"📥 Importing companies from {csv_file}...")

    if dry_run:
        click.echo("🔍 DRY RUN MODE - No changes will be made")

    try:
        imported_count = 0
        skipped_count = 0
        error_count = 0

        with get_db_session() as session:
            service = CompanyService(session)

            with open(csv_file, "r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                for row in reader:
                    try:
                        # Skip empty names
                        if not row.get("name", "").strip():
                            continue

                        # Check if company already exists
                        existing = service.get_company_by_name(row["name"])
                        if existing:
                            skipped_count += 1
                            if dry_run:
                                click.echo(f"Would skip existing: {row['name']}")
                            continue

                        # Prepare company data
                        company_data = CompanyCreate(
                            name=row["name"],
                            website=row.get("website") or None,
                            email=row.get("email") or None,
                            phone=row.get("phone") or None,
                            address_line1=row.get("address_line1") or None,
                            address_line2=row.get("address_line2") or None,
                            city=row.get("city") or None,
                            county=row.get("county") or None,
                            postcode=row.get("postcode") or None,
                            country=row.get("country") or "GB",
                            industry=row.get("industry") or None,
                            sic_code=row.get("sic_code") or None,
                            employee_count=(
                                int(row["employee_count"])
                                if row.get("employee_count", "").strip()
                                else None
                            ),
                            annual_revenue=(
                                int(row["annual_revenue"])
                                if row.get("annual_revenue", "").strip()
                                else None
                            ),
                            companies_house_number=row.get("companies_house_number")
                            or None,
                        )

                        if not dry_run:
                            company = service.create_company(company_data)
                            click.echo(f"Imported: {company.name}")
                        else:
                            click.echo(f"Would import: {company_data.name}")

                        imported_count += 1

                    except Exception as e:
                        error_count += 1
                        click.echo(f"❌ Error processing row {reader.line_num}: {e}")

        if dry_run:
            click.echo(
                f"📊 DRY RUN SUMMARY: {imported_count} would be imported, {skipped_count} would be skipped, {error_count} errors"
            )
        else:
            click.echo(
                f"✅ Import complete: {imported_count} imported, {skipped_count} skipped, {error_count} errors"
            )

    except Exception as e:
        click.echo(f"❌ Import failed: {e}")
        sys.exit(1)


@cli.command()
def stats():
    """Show application statistics."""
    click.echo("📊 Application Statistics")
    click.echo("-" * 30)

    try:
        with get_db_session() as session:
            # Basic counts
            total_companies = session.query(Company).count()
            prospects = (
                session.query(Company).filter(Company.is_prospect == True).count()
            )
            companies_house_linked = (
                session.query(Company)
                .filter(Company.companies_house_number.isnot(None))
                .count()
            )

            click.echo(f"Total companies: {total_companies}")
            click.echo(f"Prospects: {prospects}")
            click.echo(f"Companies House linked: {companies_house_linked}")

            # Country breakdown
            from sqlalchemy import func

            country_stats = (
                session.query(Company.country, func.count(Company.id).label("count"))
                .group_by(Company.country)
                .all()
            )

            click.echo("\nBy Country:")
            for country, count in country_stats:
                click.echo(f"  {country}: {count}")

            # Industry breakdown (top 5)
            industry_stats = (
                session.query(Company.industry, func.count(Company.id).label("count"))
                .filter(Company.industry.isnot(None))
                .group_by(Company.industry)
                .order_by(func.count(Company.id).desc())
                .limit(5)
                .all()
            )

            if industry_stats:
                click.echo("\nTop Industries:")
                for industry, count in industry_stats:
                    click.echo(f"  {industry}: {count}")

    except Exception as e:
        click.echo(f"❌ Failed to get statistics: {e}")
        sys.exit(1)


@cli.command()
def run_server():
    """Run the development server."""
    click.echo("🚀 Starting development server...")

    try:
        import uvicorn
        from app.main_enhanced import app

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=settings.is_development(),
            log_config=None,  # We handle our own logging
            access_log=False,  # We handle our own access logging
        )
    except ImportError:
        click.echo("❌ uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Server failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
