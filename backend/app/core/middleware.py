"""安全响应头、请求 ID、structlog 上下文绑定中间件。"""
from __future__ import annotations

import time
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """注入 X-Request-Id；同时绑定到 structlog contextvars，让所有日志带 request_id。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-Id"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """常用安全响应头。"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    """API 请求耗时埋点：observe 到 API_REQUEST_DURATION Histogram。

    route 取自 FastAPI 路由模板（如 `/api/v1/projects/{project_id}`），避免 path
    参数把 label 基数撑爆。/health 和 /metrics 本身不埋点（避免自指标污染）。
    """

    SKIP_PATHS = ("/health", "/api/v1/admin/metrics")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)
        started = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        route_template = path
        scope_route = request.scope.get("route")
        if scope_route is not None and getattr(scope_route, "path", None):
            route_template = scope_route.path
        from app.core.metrics import API_REQUEST_DURATION  # noqa: PLC0415

        API_REQUEST_DURATION.labels(
            route=route_template,
            method=request.method,
            status_code=str(response.status_code),
        ).observe(elapsed_ms)
        return response


def register_middlewares(app: FastAPI) -> None:
    # 添加顺序：后注册先执行；所以 Security 在内层、Prometheus 中间、RequestId 在最外层
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestIdMiddleware)
