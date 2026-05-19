from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.healthz import router as healthz_router
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import register_middlewares
from app.core.rate_limit import register_rate_limit
from app.core.schema import ensure_runtime_schema
from app.schemas.common import HealthResponse
from app.services.auth.service import auth_service
from app.services.model_gateway.providers import (
    AnthropicMessagesProvider,
    OpenAIChatProvider,
)
from app.services.model_gateway.service import model_gateway

configure_logging()
settings = get_settings()


def _wire_model_provider() -> None:
    """启动时按环境变量选择 provider；数据库设置会在运行时覆盖。"""
    if settings.model_gateway_mode != "real":
        return
    if settings.model_gateway_provider == "openai" and settings.openai_api_key:
        model_gateway.set_provider(
            OpenAIChatProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                timeout=settings.model_gateway_timeout_seconds,
            )
        )
    elif settings.model_gateway_provider == "anthropic" and settings.anthropic_api_key:
        model_gateway.set_provider(
            AnthropicMessagesProvider(
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
                timeout=settings.model_gateway_timeout_seconds,
            )
        )


_wire_model_provider()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "AI 小说自动生产 SaaS API。鉴权 = JWT Bearer；"
        "多租户通过 X-Organization-Id 头切换。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# 中间件顺序：CORS 必须在最外层（最先注册的最内层执行）
register_middlewares(app)
register_rate_limit(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Organization-Id", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)

register_exception_handlers(app)
app.include_router(healthz_router)
app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
async def startup() -> None:
    await ensure_runtime_schema()
    async with AsyncSessionLocal() as session:
        await auth_service.ensure_bootstrap_super_admin(session)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, environment=settings.environment)
