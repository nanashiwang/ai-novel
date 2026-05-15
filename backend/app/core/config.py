from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NovelFlow AI API"
    environment: str = "local"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://novelflow:novelflow@localhost:5432/novelflow"
    redis_url: str = "redis://localhost:6379/0"
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    model_gateway_mode: str = "mock"
    default_model: str = "gpt-4o"
    jwt_secret: str = Field(default="dev-only-change-me", min_length=8)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
