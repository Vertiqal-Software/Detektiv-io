# db/migrations/env_enhanced.py
"""
Enhanced Alembic migration environment for Detecktiv.io.

This replaces the existing env.py with improved support for:
- SQLAlchemy 2.0 models and metadata
- Better error handling and logging
- Support for both online and offline migrations
- Integration with the enhanced application structure
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import pool, create_engine, text
from dotenv import load_dotenv

# Add the project root to Python path so we can import our models
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Import our models and configuration
try:
    from app.models import Base  # This imports all models via __init__.py
    from app.core.config import settings
except ImportError as e:
    print(f"Failed to import application modules: {e}")
    print(
        "Make sure you're running from the project root and dependencies are installed"
    )
    sys.exit(1)

# Alembic Config object
config = context.config

# Interpret the config file for Python logging if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Clean any conflicting PG* environment variables that might be set by pgAdmin
for k in list(os.environ.keys()):
    if k.startswith("PG") and k not in [
        "PGPASSWORD",
        "PGUSER",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
    ]:
        os.environ.pop(k, None)

# Load environment variables
load_dotenv(project_root / ".env")

# Set target metadata for autogenerate support
target_metadata = Base.metadata


def get_database_url() -> str:
    """
    Get database URL from environment or settings.

    Uses the same configuration system as the main application
    to ensure consistency.
    """
    try:
        # Try to use the settings module first
        return settings.get_database_url()
    except Exception:
        # Fallback to manual construction if settings fail
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "")
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5432")
        database = os.getenv("POSTGRES_DB", "detecktiv")
        sslmode = os.getenv("POSTGRES_SSLMODE", "disable")

        # URL-encode credentials to handle special characters
        user_encoded = quote_plus(user)
        password_encoded = quote_plus(password)

        return f"postgresql+psycopg2://{user_encoded}:{password_encoded}@{host}:{port}/{database}?sslmode={sslmode}"


def get_database_url_masked() -> str:
    """Get database URL with password masked for logging."""
    url = get_database_url()
    if ":" in url and "@" in url:
        # Replace password with ***
        parts = url.split("://")[1].split("@")
        if len(parts) == 2:
            user_pass = parts[0]
            if ":" in user_pass:
                user = user_pass.split(":")[0]
                masked_url = url.replace(user_pass, f"{user}:***")
                return masked_url
    return url


# Set the database URL in the alembic configuration
database_url = get_database_url()
config.set_main_option("sqlalchemy.url", database_url)

print(f"Using database URL: {get_database_url_masked()}")


def include_object(object, name, type_, reflected, compare_to):
    """
    Filter objects to include in migrations.

    This function allows us to exclude certain tables or objects
    from being included in migrations.
    """
    # Skip tables that shouldn't be managed by migrations
    if type_ == "table" and name in ("alembic_version", "spatial_ref_sys"):
        return False

    return True


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Create engine with SQLAlchemy 2.0 compatibility
    connectable = create_engine(
        database_url,
        future=True,  # Enable SQLAlchemy 2.0 mode
        poolclass=pool.NullPool,  # Don't use connection pooling for migrations
        echo=False,  # Set to True for SQL debugging
    )

    with connectable.connect() as connection:
        # Test the connection
        try:
            connection.execute(text("SELECT 1"))
            print("✅ Database connection successful")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            print(
                "Please check your database configuration and ensure PostgreSQL is running"
            )
            sys.exit(1)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            # Enable autogenerate for better migration detection
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


def process_revision_directives(context, revision, directives):
    """
    Process revision directives to improve migration generation.

    This hook allows us to modify the generated migration
    before it's written to disk.
    """
    # This is where we could add custom processing of migrations
    # For example, we could:
    # - Add custom comments to migrations
    # - Skip certain types of changes
    # - Modify table or column names

    # For now, just pass through unchanged
    pass


def validate_environment():
    """Validate that the environment is properly configured."""
    required_vars = ["POSTGRES_USER", "POSTGRES_DB"]
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please ensure your .env file is properly configured")
        sys.exit(1)

    # Check if we can import required modules
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("❌ psycopg2 not available. Install with: pip install psycopg2-binary")
        sys.exit(1)


# Validate environment before running migrations
validate_environment()

# Run migrations based on context
if context.is_offline_mode():
    print("Running migrations in offline mode...")
    run_migrations_offline()
else:
    print("Running migrations in online mode...")
    run_migrations_online()
