import os
import sys
from logging.config import fileConfig
import logging

from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.engine import Connection
from alembic import context

# --------------------------------------------------------------------------------------
# Alembic Config + Logging
# --------------------------------------------------------------------------------------
config = context.config

# If you keep a logging section in alembic.ini, this wires it in:
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

# --------------------------------------------------------------------------------------
# target_metadata
# --------------------------------------------------------------------------------------
# If you later want autogenerate to pick up models, import your Base.metadata here.
# For now we keep it None to avoid import-order problems during early boot.
target_metadata = None

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
APP_SCHEMA = os.getenv("APP_SCHEMA", "app")
VERSION_TABLE = os.getenv("ALEMBIC_VERSION_TABLE", "alembic_version")

def get_url() -> str:
    """Prefer env DATABASE_URL, else fall back to sqlalchemy.url from alembic.ini."""
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url")

def _ensure_app_schema_and_search_path(conn: Connection) -> None:
    """
    Make sure the 'app' schema exists and set search_path to 'app, public'
    for the duration of the migration connection.
    """
    # 1) Create schema if needed (idempotent)
    conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{APP_SCHEMA}";')

    # 2) Set search_path so unqualified names resolve to app first
    conn.exec_driver_sql(f"SET search_path TO {APP_SCHEMA}, public;")

def _configure_context_offline():
    """
    Offline mode: Alembic outputs SQL to the screen/file, no DB connection.
    We still point Alembic at the version table inside the app schema.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
        version_table_schema=APP_SCHEMA,
        # Optional: include_schemas affects autogenerate, safe to keep False by default
        include_schemas=False,
        # Keep this True for Postgres DDL
        transactional_ddl=True,
        # Emit each migration statement as we go
        output_buffer=sys.stdout,
    )

def _configure_context_online(connection: Connection):
    """
    Online mode: we have a live DB connection.
    We ensure schema + search_path, and pin Alembic's version table into app schema.
    """
    _ensure_app_schema_and_search_path(connection)

    # (Optional) log current search_path and DB identity for diagnostics
    try:
        sp = connection.exec_driver_sql("SHOW search_path;").scalar()
        logger.info("search_path for migration connection: %s", sp)
        ident = connection.exec_driver_sql("SELECT current_database(), current_user;").fetchone()
        logger.info("DB: %s, User: %s", ident[0], ident[1])
    except Exception as e:
        logger.warning("Could not log migration diagnostics: %s", e)

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Pin version table to app schema
        version_table=VERSION_TABLE,
        version_table_schema=APP_SCHEMA,
        # Keep this True for Postgres
        transactional_ddl=True,
        # Emit SQL to logs when needed (set loggers to DEBUG to see)
        render_as_batch=False,
        # If you do autogenerate later, this hook helps keep to app schema
        include_schemas=False,
        # helpful for debugging migration order
        # compare_type=True,  # enable if you need type diffs
    )

# --------------------------------------------------------------------------------------
# Main Entrypoints
# --------------------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    _configure_context_offline()
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=get_url(),
    )

    # We want to see the first *real* error, not a cascade of
    # "current transaction is aborted" messages. So we log exceptions here.
    with connectable.connect() as connection:
        try:
            _configure_context_online(connection)

            # Ensure the version table exists inside app schema before first use.
            # Alembic will create it automatically on first upgrade, but this gives
            # us a predictable location without relying on defaults.
            connection.exec_driver_sql(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = '{APP_SCHEMA}'
                          AND table_name = '{VERSION_TABLE}'
                    ) THEN
                        -- establish the version table in the app schema
                        CREATE TABLE "{APP_SCHEMA}"."{VERSION_TABLE}" (
                            version_num VARCHAR(32) NOT NULL
                        );
                        INSERT INTO "{APP_SCHEMA}"."{VERSION_TABLE}"(version_num) VALUES ('base');
                    END IF;
                END$$;
                """
            )

            with context.begin_transaction():
                context.run_migrations()

        except Exception as e:
            # Try to surface the original PG error if present
            logger.error("Migration failed: %s", e, exc_info=True)
            # Best-effort: attempt to show the last server error message
            try:
                # Explicit rollback so subsequent attempts aren't in failed state
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                connection.close()
            except Exception:
                pass

# --------------------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
