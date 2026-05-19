"""Prometheus /metrics endpoint。

仅限平台管理员访问；避免公网暴露内部指标。Prometheus scrape 时需在
header 带上具备 platform admin 身份的 token（生产环境通常通过内网网络
策略 + bearer token 双重控制）。
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import CurrentUserDep
from app.core.metrics import render_metrics
from app.core.permissions import require_platform_admin

router = APIRouter(tags=["admin-metrics"])


@router.get("/admin/metrics")
async def metrics_endpoint(user: CurrentUserDep) -> Response:
    require_platform_admin(user)
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
