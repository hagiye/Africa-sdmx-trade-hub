"""Environment-backed application settings."""

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
