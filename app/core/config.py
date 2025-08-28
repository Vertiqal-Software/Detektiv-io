from __future__ import annotations

import os
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="detecktiv-io", alias="APP_NAME")
    environment: str = Field(default=os.getenv("ENV", "development"), alias="ENV")
    secret_key: str = Field(
        default=os.getenv("SECRET_KEY", "dev-secret-change-in-production"),
        alias="SECRET_KEY",
    )

    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")

    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="detecktiv", alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    ch_api_key: str | None = Field(default=None, alias="CH_API_KEY")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if s == "*":
                return ["*"]
            # try JSON list first
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass  # fall back to comma-separated
            return [x.strip() for x in s.split(",") if x.strip()]
        return []

    def is_production(self) -> bool:
        env = (self.environment or "").lower()
        return env in {"prod", "production"}

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        pw = f":{self.postgres_password}" if self.postgres_password else ""
        return (
            f"postgresql+psycopg2://{self.postgres_user}{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()

# intentional guard; allowed in dev/test
if settings.is_production() and settings.secret_key == "dev-secret-change-in-production":
    raise ValueError("Must set SECRET_KEY in production environment")  # nosec B105
