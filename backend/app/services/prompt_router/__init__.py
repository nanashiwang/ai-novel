"""Prompt A/B 分流路由服务对外入口。"""
from app.services.prompt_router.service import (
    PromptRouter,
    RoutingResult,
    prompt_router,
)

__all__ = ["PromptRouter", "RoutingResult", "prompt_router"]
