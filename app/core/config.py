from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Release Control"
    environment: str = "development"
    database_url: str = (
        "postgresql+asyncpg://release_control:release_control@localhost:5432/release_control"
    )
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-me"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "change-me-now"
    webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    cors_origins: list[AnyHttpUrl | str] = ["http://localhost:8000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
