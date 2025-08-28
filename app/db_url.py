# app/db_url.py
from __future__ import annotations

import os
from sqlalchemy.engine import URL


def build_sqlalchemy_url_from_env() -> URL:
    """
    Build a psycopg2 SQLAlchemy URL using env vars and *correctly* handle
    special characters in the password (e.g., @, :, /).
    """
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "detecktiv")

    # default to sslmode=disable unless overridden externally
    query = {"sslmode": os.getenv("POSTGRES_SSLMODE", "disable")}

    return URL.create(
        drivername="postgresql+psycopg2",
        username=user or None,
        password=password or None,  # URL.create will quote it safely
        host=host,
        port=port,
        database=db,
        query=query,
    )


def mask_url_password(url: URL) -> str:
    """
    Return a DSN string with the password masked for logs/health responses.
    """
    return str(
        URL.create(
            drivername=url.drivername,
            username=url.username,
            password="***" if (url.password or "") else None,
            host=url.host,
            port=url.port,
            database=url.database,
            query=url.query,
        )
    )


def db_url(mask_password: bool = True) -> str:
    """
    Back-compat convenience: return a DSN string, optionally with the password masked.

    This satisfies callers that expect a function `db_url(mask_password=...)`
    instead of working with SQLAlchemy URL objects directly.
    """
    url = build_sqlalchemy_url_from_env()
    return mask_url_password(url) if mask_password else str(url)


__all__ = ["build_sqlalchemy_url_from_env", "mask_url_password", "db_url"]
