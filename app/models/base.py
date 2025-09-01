# app/models/base.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy import DateTime, MetaData, func, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


# -----------------------------------------------------------------------------
# Default schema + naming convention (aligns ORM with Alembic and avoids drift)
# -----------------------------------------------------------------------------
def _default_schema() -> str:
    return (
        (os.getenv("POSTGRES_SCHEMA") or "").strip()
        or (os.getenv("DB_SCHEMA") or "").strip()
        or (os.getenv("ALEMBIC_SCHEMA") or "").strip()
        or "app"
    )


SCHEMA = _default_schema()

# Keep Alembic diffs stable and constraint names predictable
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_METADATA = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)

if os.getenv("SESSION_DEBUG") == "1":
    print(f"[base] Using schema: {SCHEMA}")


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    Adds common audit fields and simple (de)serialization helpers.
    Applies schema-qualified metadata to all inheriting tables.
    """

    metadata = _METADATA  # <-- schema-qualified metadata

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Record last update timestamp",
    )

    def to_dict(self, exclude: Optional[Set[str]] = None) -> Dict[str, Any]:
        exclude = exclude or set()
        result: Dict[str, Any] = {}
        for column in self.__table__.columns:  # type: ignore[attr-defined]
            if column.name in exclude:
                continue
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result

    def update_from_dict(
        self, data: Dict[str, Any], exclude: Optional[Set[str]] = None
    ) -> None:
        exclude = exclude or {"id", "created_at"}
        for key, value in data.items():
            if key not in exclude and hasattr(self, key):
                setattr(self, key, value)

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        if hasattr(self, "id"):
            return f"<{cls}(id={getattr(self, 'id', None)})>"
        return f"<{cls}>"


# -----------------------------------------------------------------------------
# Engine / Session
# - Prefer the central engine from app.core.session (single source of truth).
# - If not available, build a local engine with search_path enforcement.
# -----------------------------------------------------------------------------


def _normalize_driver(url: str) -> str:
    """
    Ensure DSN uses an explicit driver when a generic scheme is used.
    - postgres://...     -> postgresql+psycopg2://...
    - postgresql://...   -> postgresql+psycopg2://...
    """
    try:
        if "+psycopg2" in url or "+psycopg" in url or "+asyncpg" in url:
            return url
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://") :]
        return url
    except Exception:
        return url


def _build_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return _normalize_driver(url)

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    db = os.getenv("POSTGRES_DB", "detecktiv")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    sslmode = os.getenv("POSTGRES_SSLMODE")  # e.g., "disable"
    q = f"?sslmode={sslmode}" if sslmode else ""
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}{q}"


def _make_local_engine():
    """
    Build a local engine that enforces search_path and matches your original
    pool settings. This is used only if app.core.session.engine cannot be imported.

    Additive enhancements (non-breaking):
    - Optional statement timeout via STATEMENT_TIMEOUT_MS
    - Optional application_name via POSTGRES_APP_NAME / APP_NAME
    - Optional SQL echo via DB_ECHO / SESSION_ECHO_SQL
    """
    DATABASE_URL: str = _build_database_url()
    schema = SCHEMA

    # Pool & debug knobs
    pool_size = int(os.getenv("DB_POOL_SIZE", "5") or "5")
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5") or "5")
    echo_sql = (os.getenv("DB_ECHO") == "1") or (os.getenv("SESSION_ECHO_SQL") == "1")

    # Optional connection decorations
    app_name = os.getenv("POSTGRES_APP_NAME") or os.getenv("APP_NAME") or "detecktiv-io"
    stmt_timeout_ms = os.getenv("STATEMENT_TIMEOUT_MS")  # e.g., "30000"

    # psycopg(2) supports startup options via connect_args['options']
    options_parts = [f"-c search_path={schema},public"]
    if stmt_timeout_ms:
        options_parts.append(f"-c statement_timeout={int(stmt_timeout_ms)}")
    connect_args = {}
    if DATABASE_URL.startswith("postgresql"):
        connect_args["options"] = " ".join(options_parts)

    eng = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        future=True,
        connect_args=connect_args,
        echo=echo_sql,
    )

    # On-connect and on-checkout guards to keep session parameters correct for pooled conns.
    @event.listens_for(eng, "connect")
    def _set_params_on_connect(dbapi_conn, conn_record):  # type: ignore
        try:
            with dbapi_conn.cursor() as cur:
                # Create schema if not exists (non-fatal on insufficient privilege)
                try:
                    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                except Exception:  # nosec B110
                    pass
                cur.execute(f"SET search_path TO {schema}, public")
                if stmt_timeout_ms:
                    cur.execute(f"SET statement_timeout TO {int(stmt_timeout_ms)}")
                if app_name:
                    try:
                        cur.execute("SET application_name TO %s", [app_name])
                    except Exception:  # nosec B110
                        pass
        except Exception:  # nosec B110
            pass

    @event.listens_for(eng, "checkout")
    def _set_params_on_checkout(dbapi_conn, conn_record, proxy):  # type: ignore
        try:
            with dbapi_conn.cursor() as cur:
                cur.execute(f"SET search_path TO {schema}, public")
                if stmt_timeout_ms:
                    cur.execute(f"SET statement_timeout TO {int(stmt_timeout_ms)}")
        except Exception:  # nosec B110
            pass

    # Optional one-time debug check
    if os.getenv("SESSION_DEBUG") == "1":
        try:
            with eng.connect() as conn:
                sp = conn.execute(text("SHOW search_path")).scalar_one()
                try:
                    st = conn.execute(text("SHOW statement_timeout")).scalar_one()
                except Exception:
                    st = "(not supported)"
                print(f"[base] Engine check search_path={sp}; statement_timeout={st}")
        except Exception:  # nosec B110
            pass

    return eng


# Try to reuse the central engine to avoid duplicate pools/config.
try:
    from app.core.session import engine as _central_engine  # type: ignore

    engine = _central_engine
except Exception:
    engine = _make_local_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Legacy Base for older code paths; share the SAME metadata (schema + naming)
LegacyBase = declarative_base(metadata=_METADATA)


# -----------------------------------------------------------------------------
# Helper for tooling (e.g., Alembic env.py)
# -----------------------------------------------------------------------------
def get_metadata() -> MetaData:
    """Return the package-wide metadata with schema & naming convention applied."""
    return _METADATA
