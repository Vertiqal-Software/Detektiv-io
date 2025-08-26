# db/main.py
from __future__ import annotations

import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def db_url(mask_password: bool = False) -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")  # tests override to 127.0.0.1
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "detecktiv")

    safe_user = quote_plus(user)
    safe_pw = quote_plus(password)
    url = f"postgresql+psycopg2://{safe_user}:{safe_pw}@{host}:{port}/{dbname}?sslmode=disable"

    if mask_password and password:
        return url.replace(safe_pw, "***")
    return url


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(db_url(), future=True, pool_pre_ping=True)
    return _engine
