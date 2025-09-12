# app/core/config.py
from __future__ import annotations

"""
Centralised application settings for detecktiv.io

Design goals
- Single import: `from app.core.config import settings`
- Works with Pydantic v2 or v1 (fallback), but also fine without Pydantic (pure-env parsing).
- Provides a stable attribute used elsewhere: `settings.sqlalchemy_database_uri`
- Sensible defaults for local dev; all values can be overridden via env vars.

Key env vars (common)
  ENVIRONMENT=development|staging|production
  DEBUG=true|false
  LOG_LEVEL=DEBUG|INFO|WARNING|ERROR

Database (choose one)
  DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname?options=-csearch_path%3Dapp
  # or compose from parts:
  POSTGRES_HOST=localhost
  POSTGRES_PORT=5432
  POSTGRES_USER=postgres
  POSTGRES_PASSWORD=postgres
  POSTGRES_DB=detecktiv
  POSTGRES_SCHEMA=app
  POSTGRES_SSLMODE=prefer|require|disable  (default: prefer)

JWT / Auth
  SECRET_KEY=change-me
  JWT_ALG=HS256
  ACCESS_TOKEN_EXPIRES_SECONDS=900         # 15 minutes
  REFRESH_TOKEN_EXPIRES_SECONDS=1209600    # 14 days
  JWT_ISS=
  JWT_AUD=
  JWT_CLOCK_SKEW_SECONDS=60

Auth cookies (optional; used by app/api/auth.py when AUTH_COOKIES=1)
  AUTH_COOKIES=false
  AUTH_COOKIE_SECURE=true
  AUTH_COOKIE_SAMESITE=lax|strict|none
  AUTH_COOKIE_DOMAIN=
  AUTH_COOKIE_PATH=/
  AUTH_COOKIE_MAX_AGE=0                    # 0 => session cookie
  ACCESS_TOKEN_COOKIE=access_token
  REFRESH_TOKEN_COOKIE=refresh_token

CORS
  CORS_ORIGINS=http://localhost:5173,https://example.com
  CORS_ALLOW_CREDENTIALS=true
  CORS_ALLOW_METHODS=*
  CORS_ALLOW_HEADERS=*

Other
  API_ROUTER_DEBUG=0/1  (used by app/api/router.py)
"""

import os
import re
from functools import lru_cache
from typing import List, Optional


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(key)
    return v if v is not None else default


def _env_bool(key: str, default: bool = False) -> bool:
    v = (_env(key, "") or "").strip().lower()
    if v in {"1", "true", "yes", "y"}:
        return True
    if v in {"0", "false", "no", "n"}:
        return False
    return default


def _env_int(key: str, default: int) -> int:
    try:
        return int((_env(key, "") or "").strip() or default)
    except Exception:
        return default


def _split_csv(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


def _safe_schema_name(name: str, default: str = "app") -> str:
    n = (name or default).strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", n):
        return default
    return n


def _build_postgres_url() -> str:
    host = _env("POSTGRES_HOST", "localhost")
    port = _env("POSTGRES_PORT", "5432")
    user = _env("POSTGRES_USER", "postgres")
    password = _env("POSTGRES_PASSWORD", "postgres")
    db = _env("POSTGRES_DB", "detecktiv")
    schema = _safe_schema_name(_env("POSTGRES_SCHEMA", "app"))
    sslmode = _env("POSTGRES_SSLMODE", "prefer")

    # Encode search_path into options param so the schema is used by default.
    # URL-safe encoding for "-csearch_path=app".
    options = "-csearch_path%3D" + schema

    return (
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
        f"?sslmode={sslmode}&options={options}"
    )


# ------------------------------------------------------------------------------
# Settings object
# ------------------------------------------------------------------------------


class Settings:
    # Meta
    app_name: str
    environment: str
    debug: bool
    log_level: str

    # Database
    sqlalchemy_database_uri: str
    postgres_schema: str

    # JWT / Auth
    secret_key: str
    jwt_alg: str
    access_token_expires_seconds: int
    refresh_token_expires_seconds: int
    jwt_iss: Optional[str]
    jwt_aud: Optional[str]
    jwt_clock_skew_seconds: int

    # Cookies (auth)
    auth_cookies: bool
    auth_cookie_secure: bool
    auth_cookie_samesite: str
    auth_cookie_domain: str
    auth_cookie_path: str
    auth_cookie_max_age: int
    access_token_cookie: str
    refresh_token_cookie: str

    # CORS
    cors_origins: List[str]
    cors_allow_credentials: bool
    cors_allow_methods: List[str]  # '*' or specific methods
    cors_allow_headers: List[str]  # '*' or specific headers

    def __init__(self) -> None:
        # Meta
        self.app_name = _env("APP_NAME", "detecktiv.io API")
        self.environment = _env("ENVIRONMENT", "development")
        self.debug = _env_bool("DEBUG", False)
        self.log_level = _env("LOG_LEVEL", "DEBUG" if self.debug else "INFO").upper()

        # Database DSN
        db_url = _env("DATABASE_URL")
        self.postgres_schema = _safe_schema_name(_env("POSTGRES_SCHEMA", "app"))
        self.sqlalchemy_database_uri = db_url or _build_postgres_url()

        # JWT / Auth
        self.secret_key = _env("SECRET_KEY", "change-me")
        self.jwt_alg = _env("JWT_ALG", "HS256")
        self.access_token_expires_seconds = _env_int(
            "ACCESS_TOKEN_EXPIRES_SECONDS", 900
        )  # 15 min
        self.refresh_token_expires_seconds = _env_int(
            "REFRESH_TOKEN_EXPIRES_SECONDS", 14 * 86400
        )  # 14 days
        self.jwt_iss = _env("JWT_ISS", None)
        self.jwt_aud = _env("JWT_AUD", None)
        self.jwt_clock_skew_seconds = _env_int("JWT_CLOCK_SKEW_SECONDS", 60)

        # Auth cookies (optional)
        self.auth_cookies = _env_bool("AUTH_COOKIES", False)
        self.auth_cookie_secure = _env_bool("AUTH_COOKIE_SECURE", False)
        self.auth_cookie_samesite = _env(
            "AUTH_COOKIE_SAMESITE", "lax"
        ).lower()  # lax|strict|none
        self.auth_cookie_domain = _env("AUTH_COOKIE_DOMAIN", "")
        self.auth_cookie_path = _env("AUTH_COOKIE_PATH", "/")
        self.auth_cookie_max_age = _env_int("AUTH_COOKIE_MAX_AGE", 0)
        self.access_token_cookie = _env("ACCESS_TOKEN_COOKIE", "access_token")
        self.refresh_token_cookie = _env("REFRESH_TOKEN_COOKIE", "refresh_token")

        # CORS
        self.cors_origins = _split_csv(
            _env("CORS_ORIGINS", "")
        )  # empty => allow none by default
        self.cors_allow_credentials = _env_bool("CORS_ALLOW_CREDENTIALS", True)
        self.cors_allow_methods = _split_csv(_env("CORS_ALLOW_METHODS", "*")) or ["*"]
        self.cors_allow_headers = _split_csv(_env("CORS_ALLOW_HEADERS", "*")) or ["*"]

    # Convenience helpers
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_staging(self) -> bool:
        return self.environment.lower() == "staging"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in {"dev", "development", ""}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


# Singleton-style export for convenience
settings: Settings = get_settings()
