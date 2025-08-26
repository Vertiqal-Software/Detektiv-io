from __future__ import annotations

import os
from logging.config import fileConfig
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import pool, create_engine
from dotenv import load_dotenv

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Clean any PG* vars that pgAdmin may have set
for k in list(os.environ.keys()):
    if k.startswith("PG"):
        os.environ.pop(k, None)

# Load .env from project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(project_root, ".env"))

# -------------------------------------------------------------------
# ADDED (only): make sure script_location is defined even if ini isn't
# respected by the runtime invocation
try:
    current_sl = config.get_main_option("script_location", None)
except Exception:
    current_sl = None

if not current_sl:
    # Hard-code to the migrations folder in the repo
    config.set_main_option(
        "script_location", os.path.join(project_root, "db", "migrations")
    )
# -------------------------------------------------------------------

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "detecktiv")

# URL-encode creds to handle special chars like '@'
USER_Q = quote_plus(DB_USER or "")
PASS_Q = quote_plus(DB_PASS or "")

db_url = f"postgresql+psycopg2://{USER_Q}:{PASS_Q}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=disable"

# Also set libpq variables as a belt-and-braces override
os.environ["PGHOST"] = DB_HOST
os.environ["PGPORT"] = DB_PORT
os.environ["PGUSER"] = DB_USER
os.environ["PGPASSWORD"] = DB_PASS
os.environ["PGDATABASE"] = DB_NAME

# If/when you use SQLAlchemy models, set: target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=db_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        db_url,
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
