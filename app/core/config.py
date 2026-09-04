"""Environment-backed application settings."""

from functools import cached_property
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables and an optional .env file."""

    app_name: str = "Pan-African SDMX Trade Data Hub"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://postgres@localhost:55432/africa_sdmx"
    )
    sdmx_base_url: str = "https://sdmxcentral.imf.org/sdmx/v2/"
    sdmx_timeout_seconds: float = 60.0
    secret_key: str = ""
    port: int = 8000
    cors_allowed_origins: str = ""
    database_ssl_mode: str = ""
    database_pool_size: int = 2
    database_max_overflow: int = 1

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() == "production"

    @cached_property
    def sqlalchemy_database_url(self) -> str:
        """Accept common hosted-Postgres URLs while using the psycopg v3 driver."""
        value = self.database_url.strip()
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @cached_property
    def allowed_origins(self) -> list[str]:
        origins = [item.strip().rstrip("/") for item in self.cors_allowed_origins.split(",")]
        origins = [item for item in origins if item]
        if self.is_production and "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*' in production")
        return origins

    @property
    def database_host(self) -> str:
        """Return a safe host label for diagnostics; never expose credentials."""
        return urlsplit(self.sqlalchemy_database_url).hostname or "unknown"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
