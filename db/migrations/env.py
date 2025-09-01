"""
Enhanced Alembic migration environment for Detecktiv.io.

- Targets a specific schema (ALEMBIC_SCHEMA / POSTGRES_SCHEMA / DB_SCHEMA; default "app")
- Ensures the schema exists and sets search_path to "<schema>, public"
- Stores alembic_version inside that same schema (version_table_schema)
- Limits autogenerate/compare scope to the target schema
- SQLAlchemy 2.0 engine options, dotenv load, PG* var cleanup, rich logging
- Backward compatibility: automatically relocates public.alembic_version if needed

Additions (non-breaking):
- Fallback to import all app.models submodules if Base import is partial
- Safer relocation of alembic_version within a DB transaction
- Optional support for psycopg3 if psycopg2 is not installed
- Extra diagnostics and guards; no code removed from the original
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import create_engine, text, pool
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Python path to project root so we can import the app code
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables (local/dev). Try common filenames.
for env_file in (".env", ".env.local", ".env.development"):
    f = PROJECT_ROOT / env_file
    if f.exists():
        load_dotenv(f, override=False)

# ---------------------------------------------------------------------
# Alembic config + logging
# ---------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------
# Clean conflicting PG* environment variables (from tools like pgAdmin)
# ---------------------------------------------------------------------
for k in list(os.environ.keys()):
    if k.startswith("PG") and k not in {"PGPASSWORD", "PGUSER", "PGHOST", "PGPORT", "PGDATABASE"}:
        os.environ.pop(k, None)

# ---------------------------------------------------------------------
# Import models & settings (don’t hard-crash in offline/autogen edge cases)
# ---------------------------------------------------------------------
Base = None
try:
    # Original attempt: expects app/models/__init__.py to import all models
    from app.models import Base  # imports all models via package __init__
except Exception as e:  # pragma: no cover
    print(f"[alembic/env] Warning: cannot import app.models.Base ({e}); autogenerate may be limited.")
    Base = None

target_metadata = getattr(Base, "metadata", None)

# --- Additive robustness: try to import all model submodules if metadata is empty ---
if target_metadata is None:
    try:
        from importlib import import_module
        models_dir = PROJECT_ROOT / "app" / "models"
        if models_dir.exists():
            for py in models_dir.glob("*.py"):
                name = py.stem
                if name.startswith("_"):
                    continue
                try:
                    import_module(f"app.models.{name}")
                except Exception as sub_exc:
                    print(f"[alembic/env] Note: skipped import app.models.{name}: {sub_exc}")
        # Re-evaluate Base after dynamic imports
        try:
            from app.models import Base as _Base
            Base = _Base
            target_metadata = getattr(Base, "metadata", None)
            if target_metadata is not None:
                print("[alembic/env] Target metadata reloaded from app.models after dynamic imports.")
        except Exception as reimport_exc:
            print(f"[alembic/env] Fallback re-import of Base failed: {reimport_exc}")
    except Exception as dyn_exc:
        print(f"[alembic/env] Dynamic model import pass failed: {dyn_exc}")

# ---------------------------------------------------------------------
# Determine target schema and DB URL
# ---------------------------------------------------------------------
SCHEMA = (
    os.getenv("ALEMBIC_SCHEMA")
    or os.getenv("POSTGRES_SCHEMA")
    or os.getenv("DB_SCHEMA")
    or "app"
).strip() or "app"


def _build_url_from_pg_env() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "detecktiv")
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{database}?sslmode={sslmode}"
    )


def get_database_url() -> str:
    """
    Get database URL using app settings when available;
    fall back to POSTGRES_* variables.
    Tries app.core.config first, then app.config (compat shim).
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    for modpath in ("app.core.config", "app.config"):
        try:
            mod = __import__(modpath, fromlist=["settings"])
            settings = getattr(mod, "settings", None)
            if settings and hasattr(settings, "get_database_url"):
                return settings.get_database_url()
        except Exception:
            continue

    return _build_url_from_pg_env()


DATABASE_URL = get_database_url()
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def masked_url(url: str) -> str:
    if "://" in url and "@" in url:
        head, tail = url.split("://", 1)
        creds, rest = tail.split("@", 1)
        if ":" in creds:
            user = creds.split(":", 1)[0]
            return f"{head}://{user}:***@{rest}"
    return url


print(f"[alembic/env] Using database URL: {masked_url(DATABASE_URL)}")
print(f"[alembic/env] Target schema: {SCHEMA}")

# ---------------------------------------------------------------------
# Include filter: keep scope to our target schema for diffs/autogenerate
# ---------------------------------------------------------------------
def include_object(obj, name, type_, reflected, compare_to):
    """
    Limit autogenerate/compare to the target schema.
    We still allow 'alembic_version' (pinned to SCHEMA via version_table_schema).
    """
    obj_schema = getattr(obj, "schema", None)
    if obj_schema not in (None, SCHEMA):
        return False

    if type_ == "table" and name in ("spatial_ref_sys",):
        return False

    return True


# ---------------------------------------------------------------------
# Optional hook for autogenerate customization
# ---------------------------------------------------------------------
def process_revision_directives(context, revision, directives):
    return


# ---------------------------------------------------------------------
# Offline (no DB connection). Still set version_table_schema.
# ---------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("sqlalchemy.url must be set for offline migrations")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
        default_schema_name=SCHEMA,      # target schema for diffs
        version_table="alembic_version",
        version_table_schema=SCHEMA,     # version table lives in target schema
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------
# Online (with DB connection). Create schema, unify version table, run.
# ---------------------------------------------------------------------
def run_migrations_online() -> None:
    engine = create_engine(
        DATABASE_URL,
        future=True,
        poolclass=pool.NullPool,
        echo=False,
    )

    with engine.connect() as connection:
        # Ensure schema and set search path
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        connection.execute(text(f'SET search_path TO "{SCHEMA}", public'))

        # Verify connection and search_path
        try:
            ok = connection.execute(text("select 1")).scalar_one()
            if ok != 1:
                raise RuntimeError("schema ping failed")
            spath = connection.execute(text("SHOW search_path")).scalar()
            print("[alembic/env] Database connection successful")
            print(f"[alembic/env] search_path: {spath}")
        except Exception as exc:
            print(f"[alembic/env] Database connection failed: {exc}")
            print("[alembic/env] Verify DB credentials/host and that PostgreSQL is running.")
            sys.exit(1)

        # --- Additive: relocate version table inside a transaction for safety ---
        try:
            with connection.begin():
                has_public = connection.execute(
                    text(
                        "select exists ("
                        "  select 1 from information_schema.tables "
                        "  where table_schema = 'public' and table_name = 'alembic_version'"
                        ")"
                    )
                ).scalar()
                has_target = connection.execute(
                    text(
                        "select exists ("
                        "  select 1 from information_schema.tables "
                        "  where table_schema = :schema and table_name = 'alembic_version'"
                        ")"
                    ),
                    {"schema": SCHEMA},
                ).scalar()

                if has_public and not has_target:
                    print(f"[alembic/env] Relocating public.alembic_version -> {SCHEMA}.alembic_version ...")
                    connection.execute(
                        text(f'create table if not exists "{SCHEMA}"."alembic_version" (version_num varchar(32) not null)')
                    )
                    connection.execute(text(f'delete from "{SCHEMA}"."alembic_version"'))
                    connection.execute(
                        text(
                            f'insert into "{SCHEMA}"."alembic_version" (version_num) '
                            f"select version_num from public.alembic_version limit 1"
                        )
                    )
                    connection.execute(text("drop table public.alembic_version"))
                    print("[alembic/env] Relocation complete.")
        except Exception as exc:
            print(f"[alembic/env] Warning: could not verify/relocate alembic_version table ({exc}). Continuing.")

        # Configure Alembic and run migrations
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            include_schemas=True,
            compare_type=True,
            compare_server_default=True,
            default_schema_name=SCHEMA,
            version_table="alembic_version",
            version_table_schema=SCHEMA,
            render_as_batch=False,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------
# Environment validation (light-touch and accurate)
# ---------------------------------------------------------------------
def validate_environment():
    """
    - If sqlalchemy.url is available (from settings or POSTGRES_*), proceed.
    - If not, require minimal POSTGRES_* for building a DSN.
    - Only require a PG driver when running online migrations.
    """
    url = config.get_main_option("sqlalchemy.url")

    if not url:
        required_vars = ["POSTGRES_USER", "POSTGRES_DB"]
        missing = [v for v in required_vars if not os.getenv(v)]
        if missing:
            print(f"[alembic/env] Missing required environment variables: {', '.join(missing)}")
            print(
                "[alembic/env] Either set a DATABASE URL via app.core.config/app.config settings.get_database_url() "
                "or provide POSTGRES_* variables."
            )
            sys.exit(1)

    if not context.is_offline_mode():
        # Try psycopg2 first (your default), then psycopg3 as a fallback
        try:
            import psycopg2  # noqa: F401
        except Exception:
            try:
                import psycopg  # type: ignore  # noqa: F401
            except Exception:
                print("[alembic/env] No PostgreSQL driver available. Install with one of:")
                print("  - pip install psycopg2-binary   (preferred for this project)")
                print("  - pip install psycopg[binary]   (psycopg3 alternative)")
                sys.exit(1)


validate_environment()

if context.is_offline_mode():
    print("[alembic/env] Running migrations in offline mode...")
    run_migrations_offline()
else:
    print("[alembic/env] Running migrations in online mode...")
    run_migrations_online()
