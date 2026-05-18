"""Healthcheck 端点。

- /healthz/live：进程在即可，无外部依赖
- /healthz/ready：检查 DB + Redis 连通性，用于 readiness probe
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from redis import asyncio as aioredis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/healthz/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/healthz/ready")
async def readiness() -> dict:
    settings = get_settings()
    checks: dict[str, str] = {}

    async def check_db():
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {exc.__class__.__name__}"

    async def check_redis():
        try:
            client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await client.ping()
            await client.aclose()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc.__class__.__name__}"

    await asyncio.gather(check_db(), check_redis())
    ready = all(v == "ok" for v in checks.values())
    return {"status": "ok" if ready else "degraded", "checks": checks}
