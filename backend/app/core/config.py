from functools import lru_cache

import json

from pydantic import Field, model_validator
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
    temporal_enabled: bool = False
    model_gateway_mode: str = "mock"
    model_gateway_provider: str = "openai"  # openai | anthropic
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    default_model: str = "gpt-5.5"

    # 鉴权与会话
    jwt_secret: str = Field(default="dev-only-change-me", min_length=8)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "novelflow-api"
    jwt_audience: str = "novelflow-client"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    bcrypt_rounds: int = 12

    # 跨域
    cors_origins: str = "http://localhost:13000,http://127.0.0.1:13000"

    # Cookie
    refresh_cookie_name: str = "novelflow_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: str = "lax"

    # DB 连接池
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True

    # 限流（slowapi）
    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_default: str = "120/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip().strip("'").strip('"')
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                raw = raw.strip("[]")
        return [
            item.strip().strip("'").strip('"')
            for item in raw.split(",")
            if item.strip().strip("'").strip('"')
        ]

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        """生产环境必须使用强密钥，且 CORS 不能与 credentials 冲突。"""
        if self.environment in {"production", "prod"}:
            if self.jwt_secret in {"dev-only-change-me", "please-change-me-in-production-min-32-chars"}:
                raise ValueError("JWT_SECRET 在生产环境必须替换为强随机密钥（≥32 字符）")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET 在生产环境必须 ≥32 字符")
            if not self.refresh_cookie_secure:
                raise ValueError("生产环境 REFRESH_COOKIE_SECURE 必须为 true")
        if "*" in self.cors_origin_list:
            raise ValueError(
                "CORS_ORIGINS 不能包含 '*'（与 allow_credentials=true 冲突）"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
