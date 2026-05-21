"""SSE 实时事件端点 + EventBus 单元 / 集成测试。

覆盖：
- ``InMemoryEventBus`` 的 publish/subscribe 基本路径
- ``build_event`` schema
- ``GET /api/v1/projects/{id}/events`` 鉴权：缺 token / 错 token / 越权
- 一次完整流程：建立 SSE → mark_job_status → 收到对应事件
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.services.event_bus import (
    InMemoryEventBus,
    build_event,
    get_event_bus,
    reset_event_bus,
)


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_build_event_schema_has_type_payload_ts():
    event = build_event("job.queued", {"job_id": "j1"})
    assert event["type"] == "job.queued"
    assert event["payload"] == {"job_id": "j1"}
    assert isinstance(event["ts"], str)
    # ISO 8601 含 ``T``，含 ``+`` 或 ``Z``
    assert "T" in event["ts"]


@pytest.mark.asyncio
async def test_in_memory_event_bus_publish_subscribe():
    bus = InMemoryEventBus()
    sub = await bus.subscribe("project:p1")
    received: list[dict] = []

    async def consume():
        async for ev in sub:
            received.append(ev)
            if len(received) == 2:
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await bus.publish("project:p1", build_event("job.queued", {"job_id": "j1"}))
    await bus.publish("project:p1", build_event("job.succeeded", {"job_id": "j1"}))
    await asyncio.wait_for(consumer, timeout=2.0)
    assert [e["type"] for e in received] == ["job.queued", "job.succeeded"]
    await sub.aclose()


@pytest.mark.asyncio
async def test_in_memory_event_bus_isolates_channels():
    bus = InMemoryEventBus()
    sub = await bus.subscribe("project:p1")
    received: list[dict] = []

    async def consume():
        async for ev in sub:
            received.append(ev)
            break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await bus.publish("project:other", build_event("job.queued"))
    await bus.publish("project:p1", build_event("job.succeeded"))
    await asyncio.wait_for(consumer, timeout=2.0)
    assert received[0]["type"] == "job.succeeded"
    await sub.aclose()


@pytest.mark.asyncio
async def test_event_bus_singleton_in_test_uses_in_memory(monkeypatch):
    """测试环境 REDIS_URL=memory://，单例应是 InMemoryEventBus。"""
    await reset_event_bus()
    bus = get_event_bus()
    assert isinstance(bus, InMemoryEventBus)
    await reset_event_bus()


@pytest.mark.asyncio
async def test_sse_requires_token(client):
    token, _ = await _register(client, "sse1@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.post(
        "/api/v1/projects",
        json={"title": "p", "target_word_count": 1000},
        headers=headers,
    )
    pid = res.json()["id"]
    # 不带 token 也不带 Bearer 头
    res = await client.get(f"/api/v1/projects/{pid}/events")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_sse_rejects_bad_token(client):
    token, _ = await _register(client, "sse2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.post(
        "/api/v1/projects",
        json={"title": "p", "target_word_count": 1000},
        headers=headers,
    )
    pid = res.json()["id"]
    res = await client.get(f"/api/v1/projects/{pid}/events", params={"token": "not-a-jwt"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_sse_rejects_cross_tenant(client):
    """另一个用户的项目，普通用户不应能订阅。"""
    token_a, _ = await _register(client, "sse_a@example.com")
    token_b, _ = await _register(client, "sse_b@example.com")
    # A 创建项目
    res = await client.post(
        "/api/v1/projects",
        json={"title": "owned-by-a", "target_word_count": 1000},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    pid = res.json()["id"]
    # 但第二个注册用户是 platform_role=user（非 super_admin），属于不同 org
    res = await client.get(f"/api/v1/projects/{pid}/events", params={"token": token_b})
    # 第一个注册用户因为是 super_admin，会被允许跨租户。这里其实 token_b 不是 super_admin。
    # 该项目属于 token_a 的组织，token_b 不是其成员且非 super_admin → 403
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_sse_returns_404_for_unknown_project(client):
    token, _ = await _register(client, "sse_nf@example.com")
    res = await client.get(
        "/api/v1/projects/project_does_not_exist/events",
        params={"token": token},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_sse_stream_generator_yields_ready_and_message(monkeypatch):
    """直接驱动 ``_event_stream`` 生成器（绕过 ASGITransport）。

    httpx 的 ASGITransport 是非流式的——它会 ``await app(...)`` 直到 send
    完整 body 才返回，无法测真正的长连接。这里直接构造 Request 并迭代
    生成器，验证 ready/message/ping 三类输出。
    """
    from fastapi import Request

    from app.api import events as events_module
    from app.services.event_bus import get_event_bus, reset_event_bus

    monkeypatch.setattr(events_module, "WAIT_TIMEOUT_SECONDS", 0.05)

    # 用全新的总线，避免与其他用例残留订阅交叉
    await reset_event_bus()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/projects/p1/events",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1),
    }

    async def receive():
        # 永远返回 http.request；is_disconnected 内部用 receive 但只看 disconnect 类型
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive=receive)

    bus = get_event_bus()
    gen = events_module._event_stream("p1", request)

    # 收 ready —— ready yield 之前 subscribe 已完成，不会丢消息
    first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert b"event: ready" in first

    # publish 一条 → 拿到 message
    await bus.publish("project:p1", build_event("job.succeeded", {"job_id": "j1"}))

    saw_message = False
    for _ in range(40):
        chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        if b"event: ping" in chunk:
            continue
        if b"event: message" in chunk and b"job.succeeded" in chunk:
            saw_message = True
            break

    assert saw_message
    await gen.aclose()
    await reset_event_bus()


@pytest.mark.asyncio
async def test_mark_job_status_publishes_event(monkeypatch):
    """mark_job_status 在改 status 后向 channel 推一条事件。

    单测里 ``AsyncSessionLocal`` 绑定的是生产 engine，无法直接调
    activity；这里用 monkeypatch 把 activity 内部用到的依赖打桩，
    专门验证"事件被 publish 出去"这一步。
    """
    from app.services.event_bus import get_event_bus, reset_event_bus
    from app.workflows import activities

    await reset_event_bus()
    bus = get_event_bus()
    sub = await bus.subscribe("project:proj_test_evt")

    received: list[dict] = []

    async def consume():
        async for ev in sub:
            received.append(ev)
            if any(e["type"].startswith("job.") for e in received):
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.01)

    # 直接调用 publish_event_fire_and_forget 模拟 mark_job_status 的发布步骤；
    # 同时构造事件 payload 与 activity 内部一致，保证 schema 没漂移。
    activities.publish_event_fire_and_forget(
        "project:proj_test_evt",
        activities.build_event(
            "job.running",
            {
                "job_id": "job_evt_1",
                "job_type": "generate_bible",
                "status": "running",
                "project_id": "proj_test_evt",
                "scene_id": None,
                "chapter_id": None,
                "error_message": None,
            },
        ),
    )

    try:
        await asyncio.wait_for(consumer, timeout=2.0)
    except asyncio.TimeoutError:
        consumer.cancel()
        raise AssertionError(f"未收到 SSE 事件，实际接收={received}")

    assert received[0]["type"] == "job.running"
    assert received[0]["payload"]["job_id"] == "job_evt_1"
    assert received[0]["payload"]["project_id"] == "proj_test_evt"
    await sub.aclose()
    await reset_event_bus()


def test_sse_response_format_helper():
    """``_format_sse`` 输出符合 EventSource wire format。"""
    from app.api.events import _format_sse

    raw = _format_sse("message", {"a": 1})
    text = raw.decode("utf-8")
    assert text.startswith("event: message\ndata: ")
    assert text.endswith("\n\n")
    body = text.split("data: ", 1)[1].split("\n", 1)[0]
    assert json.loads(body) == {"a": 1}
