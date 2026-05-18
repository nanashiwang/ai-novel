"""slowapi 限流配置。

策略：默认按 IP 限流；对 /auth/login、/auth/register 做更严格的策略。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.redis_url,
    strategy="moving-window",
)


def register_rate_limit(app: FastAPI) -> None:
    if not settings.rate_limit_enabled:
        limiter.enabled = False
        return
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


# 装饰器：仅在路由层使用，避免与 Depends 冲突
def login_limit(request: Request):  # 占位：装饰器直接在 route 上使用 @limiter.limit(...)
    return request
