"""Healthz 端点测试。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_liveness(client):
    res = await client.get("/healthz/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_does_not_crash(client):
    # readiness 可能报告 degraded（测试环境无 redis），但端点必须可用
    res = await client.get("/healthz/ready")
    assert res.status_code == 200
    assert "checks" in res.json()
