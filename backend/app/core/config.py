import json
from functools import lru_cache

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
    model_gateway_provider: str = "openai"  # openai | anthropic
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    default_model: str = "gpt-5.5"
    model_gateway_timeout_seconds: float = 300.0
    # 长输出后台任务（如全项目重构提案）允许比普通请求更久。
    model_gateway_long_timeout_seconds: float = 900.0

    # Sprint 14-C3 多 agent 场景写作：
    # - "single"（默认）：保留原 WriterService.write_scene_draft 单次 JSON 生成路径
    # - "multi"：planner → drafter → stylist 三步流水线，token 消耗显著升高，
    #   由 quota 系统控制，不在此处强制上限
    writer_pipeline_mode: str = "single"

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

    # 对象存储（MinIO / S3-compatible）
    # 默认 enabled=false：导出文件直接存 ExportFile.content（db）。
    # enabled=true 时通过 storage abstraction 上传到 MinIO，file_url 改为
    # 预签名下载 URL（默认 1h 有效）。
    minio_enabled: bool = False
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "novelflow-exports"
    minio_secure: bool = False  # http vs https
    minio_presigned_ttl_seconds: int = 3600

    # 内容审查（Sprint 13-A3）
    # provider="local" 仅走本地正则；"openai" 叠加 OpenAI moderation API
    moderation_enabled: bool = True
    moderation_provider: str = "local"
    moderation_block_severity: str = "high"  # 达到此严重度时调用方应阻断写入

    # 嵌入向量（Sprint 13-B1）
    # provider="stub" 走本地确定性向量（无外部依赖，单测可用）；
    # provider="openai" 走 text-embedding-3-small（1536 维）
    embedding_provider: str = "stub"
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536

    # 章内同步推演（Sprint 16-E4）
    # 默认 False：批量章模式（write_scene_drafts / write_chapter_scenes_for_full_novel）
    # 不在 scene 写完后跑 character/world/plot extract，保持原吞吐。
    # 设为 True 时会与 single scene workflow 行为对齐，每场后同步落 pending
    # revisions——延迟会涨 30-50%，但与 character_revisions 审核闭环更紧。
    inchapter_extract_enabled: bool = False

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
            if self.jwt_secret in {
                "dev-only-change-me",
                "please-change-me-in-production-min-32-chars",
            }:
                raise ValueError("JWT_SECRET 在生产环境必须替换为强随机密钥（≥32 字符）")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET 在生产环境必须 ≥32 字符")
            if not self.refresh_cookie_secure:
                raise ValueError("生产环境 REFRESH_COOKIE_SECURE 必须为 true")
        if "*" in self.cors_origin_list:
            raise ValueError(
                "CORS_ORIGINS 不能包含 '*'（与 allow_credentials=true 冲突）"
            )
        if self.writer_pipeline_mode not in {"single", "multi"}:
            raise ValueError(
                "WRITER_PIPELINE_MODE 必须是 'single' 或 'multi'，"
                f"当前值={self.writer_pipeline_mode!r}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
