"""Healthcheck 端点（Sprint 13-A2 升级）。

约定：
- /healthz/live：仅检查进程存活，无外部依赖（k8s liveness probe）
- /healthz/ready：DB + Redis + 启用的 MinIO/Temporal，degraded 返 503（k8s readiness）
- /healthz/startup：与 ready 同语义但允许更长超时，用于 startup probe

设计要点：
1. 每个 check 有独立超时（默认 2s），任一卡死不会拖垮整个端点
2. 仅启用的依赖参与判断（MinIO/Temporal 未开启则跳过）
3. 输出 per-check {status, latency_ms[, error]}，便于排障
4. degraded 时返回 HTTP 503，让 LB/k8s 自动剔除节点
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response, status
from redis import asyncio as aioredis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

router = APIRouter(tags=["health"])

CheckFn = Callable[[], Awaitable[None]]
_DEFAULT_TIMEOUT_S = 2.0
_STARTUP_TIMEOUT_S = 10.0


async def _run_check(name: str, fn: CheckFn, timeout: float) -> dict:
    """执行单项 check，统一收敛超时与异常为结构化结果。"""
    start = time.perf_counter()
    try:
        await asyncio.wait_for(fn(), timeout=timeout)
        return {
            "name": name,
            "status": "ok",
            "latency_ms": int((time.perf_counter() - start) * 1000),
        }
    except asyncio.TimeoutError:
        return {
            "name": name,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": f"timeout>{timeout}s",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
        }


async def _check_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    settings = get_settings()
    client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def _check_minio() -> None:
    """MinIO bucket 存在性检查（仅 enabled 时启用）。"""
    settings = get_settings()
    from minio import Minio  # noqa: PLC0415 - lazy import 与 storage 一致

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    # bucket_exists 是同步调用，丢到默认线程池避免阻塞 event loop
    await asyncio.get_running_loop().run_in_executor(
        None, client.bucket_exists, settings.minio_bucket
    )


async def _check_temporal() -> None:
    """Temporal 连通性检查（仅 enabled 时启用）。"""
    settings = get_settings()
    from temporalio.client import Client  # noqa: PLC0415

    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    # Client.connect 成功即认为可达；不做 list_workflows 等重操作
    _ = client


def _build_checks(settings) -> list[tuple[str, CheckFn]]:
    checks: list[tuple[str, CheckFn]] = [
        ("database", _check_db),
        ("redis", _check_redis),
    ]
    if settings.minio_enabled:
        checks.append(("minio", _check_minio))
    if settings.temporal_enabled:
        checks.append(("temporal", _check_temporal))
    return checks


async def _readiness_payload(response: Response, timeout: float) -> dict:
    settings = get_settings()
    checks = _build_checks(settings)
    results = await asyncio.gather(
        *(_run_check(name, fn, timeout) for name, fn in checks)
    )
    ready = all(r["status"] == "ok" for r in results)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready else "degraded",
        "checks": {r["name"]: {k: v for k, v in r.items() if k != "name"} for r in results},
    }


@router.get("/healthz/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/healthz/ready")
async def readiness(response: Response) -> dict:
    return await _readiness_payload(response, _DEFAULT_TIMEOUT_S)


@router.get("/healthz/startup")
async def startup_probe(response: Response) -> dict:
    """启动探针——允许较长超时，给慢启动依赖（如冷启动的 Temporal）留余量。"""
    return await _readiness_payload(response, _STARTUP_TIMEOUT_S)
