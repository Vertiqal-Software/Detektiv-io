#!/usr/bin/env python3
"""
Schema sanity checks using the same URL & schema logic as Alembic env.py.

- Prints search_path
- Lists tables in target schema
- Shows columns for key tables (tenants, companies, source_events) if they exist
- Lists primary/unique constraints on app.companies (fixed: no regclass bind)
- Lists indexes on app.companies
- Prints alembic version stored in DB, and (if available) the repo head revision

Safe: read-only; no schema changes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus
from typing import List, Tuple, Optional

from sqlalchemy import create_engine, text

# Optional: Alembic head comparison (non-fatal if missing)
try:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    _ALEMBIC_AVAILABLE = True
except Exception:
    _ALEMBIC_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env like env.py
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass


def _schema() -> str:
    return (
        os.getenv("ALEMBIC_SCHEMA")
        or os.getenv("POSTGRES_SCHEMA")
        or os.getenv("DB_SCHEMA")
        or "app"
    ).strip() or "app"


def _alembic_ini_path() -> str:
    # Mirrors how tooling usually resolves it
    return os.getenv("ALEMBIC_CONFIG") or str(PROJECT_ROOT / "alembic.ini")


def _database_url() -> str:
    # Prefer app settings if available
    try:
        from app.core.config import settings  # type: ignore
        url = settings.get_database_url()
        if url:
            return url
    except Exception:
        pass

    # DATABASE_URL override
    dburl = os.getenv("DATABASE_URL")
    if dburl:
        return dburl

    # Fallback: POSTGRES_* environment variables
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


def _print_table_columns(conn, schema: str, table: str) -> None:
    cols = conn.execute(text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema=:s AND table_name=:t
        ORDER BY ordinal_position
    """), {"s": schema, "t": table}).all()
    if not cols:
        print(f"- {schema}.{table}: (missing)")
        return
    print(f"- {schema}.{table}:")
    for name, dtype, nullable, default in cols:
        nn = "NOT NULL" if (nullable or "").upper() == "NO" else "NULL"
        print(f"    {name} :: {dtype} :: {nn} :: default={default}")


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(conn.execute(text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema=:s AND table_name=:t AND table_type='BASE TABLE'
        )
    """), {"s": schema, "t": table}).scalar())


def _row_count(conn, schema: str, table: str) -> Optional[int]:
    if not _table_exists(conn, schema, table):
        return None
    return conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar()


def _print_constraints(conn, schema: str, table: str) -> None:
    # Use pg_catalog joins; do not bind regclass
    cons: List[Tuple[str, str]] = conn.execute(text("""
        SELECT c.conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = :schema
          AND rel.relname = :table
          AND c.contype IN ('p','u')
        ORDER BY c.conname
    """), {"schema": schema, "table": table}).all()
    if cons:
        print(f"Constraints on {schema}.{table}:")
        for name, defn in cons:
            print(f"  - {name}: {defn}")
    else:
        print(f"No PK/UNIQUE constraints found on {schema}.{table} (table missing or no constraints).")


def _print_indexes(conn, schema: str, table: str) -> None:
    # List indexes with definitions
    idxs = conn.execute(text("""
        SELECT i.relname AS index_name, pg_get_indexdef(ix.indexrelid) AS idx_def
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = :schema
          AND t.relname = :table
        ORDER BY i.relname
    """), {"schema": schema, "table": table}).all()
    if idxs:
        print(f"Indexes on {schema}.{table}:")
        for name, ddl in idxs:
            print(f"  - {name}: {ddl}")
    else:
        print(f"No indexes found on {schema}.{table}.")


def _repo_head_revision() -> Optional[str]:
    if not _ALEMBIC_AVAILABLE:
        return None
    try:
        cfg = Config(_alembic_ini_path())
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        if len(heads) == 1:
            return heads[0]
        # Multiple heads or none: return a hint string
        return ",".join(heads) if heads else None
    except Exception:
        return None


def main() -> None:
    schema = _schema()
    url = _database_url()

    print(f"Target schema: {schema}")
    print("Connecting...")
    eng = create_engine(url, future=True)

    with eng.connect() as conn:
        # Show search_path
        spath = conn.execute(text("SHOW search_path")).scalar()
        print(f"search_path: {spath}")

        # List tables in target schema
        tables = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema=:s AND table_type='BASE TABLE'
            ORDER BY table_name
        """), {"s": schema}).scalars().all()
        print(f"Tables in {schema}: {tables or '— none —'}")

        # Show columns for key tables if present
        for t in ["tenants", "companies", "source_events"]:
            _print_table_columns(conn, schema, t)

        # Row counts (if present)
        for t in ["tenants", "users", "companies", "source_events"]:
            cnt = _row_count(conn, schema, t)
            if cnt is not None:
                print(f"Row count {schema}.{t}: {cnt}")

        # Constraints & indexes on companies
        _print_constraints(conn, schema, "companies")
        _print_indexes(conn, schema, "companies")

        # Alembic version stored in DB
        has_version = conn.execute(text("""
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema=:s AND table_name='alembic_version'
            )
        """), {"s": schema}).scalar_one()
        db_rev = None
        if has_version:
            db_rev = conn.execute(text(f'SELECT version_num FROM "{schema}"."alembic_version"')).scalar()
            print(f"{schema}.alembic_version = {db_rev}")
        else:
            print(f"{schema}.alembic_version table not found")

        # Repo head (optional) and comparison
        repo_head = _repo_head_revision()
        if repo_head:
            print(f"Repo head revision = {repo_head}")
            if db_rev and db_rev != repo_head:
                print(f"[WARN] DB stored revision != repo head ({db_rev} != {repo_head}). "
                      f"If schema is correct, you may stamp: alembic -c ./alembic.ini stamp head")
        else:
            print("(Alembic not available or unable to determine repo head; skipping head comparison)")

    print("OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
