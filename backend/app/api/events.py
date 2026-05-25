"""SSE 实时事件端点。

替代前端 1.5s 轮询。客户端通过 ``EventSource(/api/v1/projects/{project_id}/events?token=...)``
建立长连接，后端把 ``project:{project_id}`` channel 上的事件实时推送过去。

设计：

- 鉴权：``EventSource`` API 不支持自定义 header，因此 access_token 通过
  query string ``?token=<jwt>`` 传递；服务端在这里手工解析 JWT，复用
  ``UserRepository`` 校验用户活跃。
- 多租户隔离：解析出 ``preferred_organization_id`` + 验证用户对该项目
  所属 organization 是 active member（或平台管理员）。
- 心跳：每 30s 发一条 ``event: ping``，让代理 / 浏览器不要超时断开。
- 断开清理：``StreamingResponse`` 的生成器退出时 ``EventBus.subscribe``
  自动 unsubscribe，无需显式清理。
- 失败兜底：解析 token / 找用户 / 找项目失败统一返回 401/403/404；
  连接建立后 channel 异常会被记录但不向浏览器抛错（避免重连风暴）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.jwt_tokens import decode_token
from app.models.organization import OrganizationMember
from app.repositories import ProjectRepository, UserRepository
from app.services.event_bus import build_event, get_event_bus

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["events"])

# SSE 流相关常量
HEARTBEAT_INTERVAL_SECONDS = 30.0
# 等待下一条事件的最长时间，到点了发心跳并重新等待
WAIT_TIMEOUT_SECONDS = HEARTBEAT_INTERVAL_SECONDS


async def _resolve_user_and_project(
    session: AsyncSession,
    *,
    token: str,
    project_id: str,
) -> tuple[str, str]:
    """复用 JWT 校验 + 项目归属校验。返回 ``(user_id, organization_id)``。"""
    payload = decode_token(token, expected_type="access")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

    user_repo = UserRepository(session)
    user = await user_repo.get(user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_inactive")

    # 找项目，再用 project.organization_id 做归属校验
    project = await ProjectRepository(session).get(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")

    member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == project.organization_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.status == "active",
            )
        )
    ).scalar_one_or_none()
    if member is None and user.platform_role not in {"admin", "super_admin"}:
        # 非成员且非平台管理员 → 403
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant_not_allowed")

    return user.id, project.organization_id


def _format_sse(event_type: str, data: dict | str) -> bytes:
    """按 EventSource wire format 序列化。空行结尾标识一条完整 event。"""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n".encode()


async def _event_stream(
    project_id: str,
    request: Request,
) -> AsyncIterator[bytes]:
    """SSE 主流。

    顺序：
    1. ``await bus.subscribe(channel)`` —— 该调用在返回前完成订阅注册
       （InMemory：把队列加入 _subscribers；Redis：发送 SUBSCRIBE 并等
       响应），保证之后 publish 不会因竞态丢失。
    2. yield ``ready`` 让前端知道连接已就绪可以开始 push。
    3. 后台 ``_pump`` 把订阅事件搬运到本地队列；主循环对队列 ``get``
       做 ``wait_for``，超时则发心跳。
       （直接 ``wait_for(subscription.__anext__())`` 会在超时时取消
       生成器导致下次迭代抛 ``StopAsyncIteration``，无法持续订阅。）
    4. 客户端断开 / 后台 Task 异常 → finally 取消任务并关订阅。
    """
    bus = get_event_bus()
    channel = f"project:{project_id}"

    subscription = await bus.subscribe(channel)
    inbox: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for event in subscription:
                await inbox.put(event)
        except Exception:  # noqa: BLE001
            _logger.exception("event_bus subscribe pump failed channel=%s", channel)
        finally:
            await inbox.put(None)

    pump_task = asyncio.create_task(_pump())

    yield _format_sse("ready", {"channel": channel})

    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(inbox.get(), timeout=WAIT_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                yield _format_sse("ping", build_event("ping"))
                continue
            if event is None:
                break
            yield _format_sse("message", event)
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await subscription.aclose()
        except Exception:  # noqa: BLE001
            pass


@router.get("/{project_id}/events", include_in_schema=True)
async def project_events_stream(
    project_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token: Annotated[str | None, Query(description="access token，EventSource 不支持自定义 header")] = None,
):
    """打开项目维度的 SSE 流。

    用法（前端）：

    .. code-block:: ts

       const es = new EventSource(`/api/v1/projects/${id}/events?token=${jwt}`);
       es.addEventListener('message', e => { ... });

    事件分类：

    - ``event: ready`` 订阅就绪
    - ``event: ping`` 30s 心跳
    - ``event: message`` 业务事件（``job.queued/running/...``、
      ``character_revision.created`` 等）
    """
    if not token:
        # 兼容 Authorization 头（用 fetch / curl 直接订阅时）：从请求里读 Bearer
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")

    # 鉴权：在打开流之前完成；失败直接抛 HTTPException
    await _resolve_user_and_project(session, token=token, project_id=project_id)

    return StreamingResponse(
        _event_stream(project_id, request),
        media_type="text/event-stream",
        headers={
            # 关闭代理缓冲，确保心跳真的能 30s 一次到达浏览器
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
