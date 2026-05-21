"""Healthz 端点测试（Sprint 13-A2）。

覆盖：
- liveness：始终 200，无外部依赖
- readiness：结构正确，包含 database/redis；degraded 时返回 503
- startup：与 ready 同结构，但端点存在且可调
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_liveness(client):
    res = await client.get("/healthz/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_structure(client):
    # 测试环境无 redis：端点必须可用，但允许 degraded
    res = await client.get("/healthz/ready")
    assert res.status_code in (200, 503)
    body = res.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body
    assert "database" in body["checks"]
    assert "redis" in body["checks"]
    # 每项 check 都应有 status + latency_ms
    for name, info in body["checks"].items():
        assert "status" in info, name
        assert "latency_ms" in info, name


@pytest.mark.asyncio
async def test_readiness_degraded_returns_503(client):
    # 复用 test_readiness_structure 的逻辑——如果有 check error，必须 503
    res = await client.get("/healthz/ready")
    body = res.json()
    has_error = any(info["status"] != "ok" for info in body["checks"].values())
    if has_error:
        assert res.status_code == 503
        assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_startup_probe(client):
    res = await client.get("/healthz/startup")
    assert res.status_code in (200, 503)
    body = res.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body
