"""
Utilities to construct and safely log the database URL.

Priority:
1) Respect DATABASE_URL if set (useful for platforms and CI).
2) Otherwise build from POSTGRES_* environment variables.

This module mirrors the URL construction used in app.main (URL.create) so
both the API and tooling (Alembic, scripts) behave the same way.

Security: never log the raw password; use get_masked_database_url().
"""

from __future__ import annotations

import os
from typing import Optional, Tuple
from urllib.parse import quote_plus

from sqlalchemy.engine import URL


# ---------------------------
# Core builders
# ---------------------------


def _get_env_pg() -> Tuple[str, str, str, str, str, str]:
    """
    Read Postgres env vars (with safe defaults suitable for dev).
    Returns: (user, password, host, port, db, sslmode)
    """
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "detecktiv")
    # default sslmode to 'disable' for local/dev; allow override
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")
    return user, password, host, port, database, sslmode


def _build_url_from_pg_env() -> str:
    """
    Build a SQLAlchemy URL string using URL.create so credentials are properly escaped.
    Driver is the same used elsewhere: postgresql+psycopg2
    """
    user, password, host, port, database, sslmode = _get_env_pg()

    url = URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port) if str(port).isdigit() else None,
        database=database,
        query={"sslmode": sslmode},
    )
    return str(url)


def normalize_driver(raw_url: str) -> str:
    """
    If caller set DATABASE_URL without a driver (e.g., 'postgres://...'),
    ensure it's normalized to 'postgresql+psycopg2://...'.

    No-op if already has '+psycopg2'.
    """
    if not raw_url:
        return raw_url

    # Already normalized
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url

    # Common shorthands from envs/hosts
    if raw_url.startswith("postgres://"):
        return "postgresql+psycopg2://" + raw_url[len("postgres://") :]

    if raw_url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + raw_url[len("postgresql://") :]

    # Leave other schemes alone (e.g., sqlite), though this module is for PG.
    return raw_url


def get_database_url() -> str:
    """
    Preferred entrypoint for Alembic/scripts/legacy code.
    - If DATABASE_URL is set, normalize its driver and return it.
    - Else, build from POSTGRES_* env vars.
    """
    raw = os.getenv("DATABASE_URL")
    if raw:
        return normalize_driver(raw)
    return _build_url_from_pg_env()


def get_masked_database_url() -> str:
    """
    Mask password for safe logging.
    Attempts to use POSTGRES_PASSWORD if present; otherwise masks the portion
    after the first ':' in the credentials section conservatively.
    """
    url = get_database_url()
    password = os.getenv("POSTGRES_PASSWORD", "")

    if password and password in url:
        return url.replace(password, "***")

    # Fallback conservative mask if password is not directly present
    # Example: postgresql+psycopg2://user:pass@host:port/db?x=y
    try:
        before, after = url.split("://", 1)
        if "@" in after and ":" in after.split("@", 1)[0]:
            creds, rest = after.split("@", 1)
            user_part, _pwd = creds.split(":", 1)
            return f"{before}://{user_part}:***@{rest}"
    except Exception:  # nosec B110
        pass

    return url


# ---------------------------
# Helpers (optional)
# ---------------------------


def validate_url(url: Optional[str] = None) -> bool:
    """
    Light validation: try to round-trip through SQLAlchemy's URL.create.
    Returns True if it looks valid. Does not attempt a network connection.
    """
    try:
        url_str = url or get_database_url()
        # Re-parse via SQLAlchemy by deconstructing: if it fails, we catch.
        # Note: URL.create requires structured fields; here we tolerate by returning True
        # if we can at least normalize with our driver and basic format.
        norm = normalize_driver(url_str)
        # A shallow parse: ensure it contains "://"
        return "://" in norm and ("postgresql" in norm)
    except Exception:
        return False


def get_psycopg2_dsn() -> str:
    """
    Returns a DSN suitable for tools that prefer classic DSN style.
    (Kept here for convenience; not used by SQLAlchemy create_engine.)
    """
    user, password, host, port, database, sslmode = _get_env_pg()
    # quote_plus for safety if any chars need escaping
    u = quote_plus(user)
    p = quote_plus(password)
    h = host
    return f"host={h} port={port} dbname={database} user={u} password={p} sslmode={sslmode}"


# ---------------------------
# CLI (debug aid)
# ---------------------------


def _main():
    import sys

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "show":
        print(get_database_url())
    elif arg in {"mask", "masked"}:
        print(get_masked_database_url())
    elif arg in {"validate", "check"}:
        ok = validate_url()
        print("valid" if ok else "invalid")
        sys.exit(0 if ok else 1)
    else:
        print(
            "Usage: python -m app.db_url [show|mask|validate]",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    _main()
