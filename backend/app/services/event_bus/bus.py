"""事件总线实现。

服务端通过 ``EventBus.publish(channel, event)`` 把任务状态变化推到
``channel = project:{project_id}``；API 层 ``/api/v1/projects/{id}/events``
打开 SSE，使用 ``subscribe(channel)`` 接收事件后转发给浏览器 EventSource。

设计要点：

- ``EventBus`` 是 Protocol，便于在测试里注入 fake。
- ``RedisEventBus`` 用 ``redis.asyncio`` 的 pub/sub；每次 ``subscribe`` 都
  新开一个 ``PubSub`` 实例，订阅完成后调用方负责通过 ``async for`` 消费；
  生成器退出时自动 ``unsubscribe + close``，不会泄漏连接。
- ``InMemoryEventBus`` 在进程内维护 ``channel -> set[asyncio.Queue]``，
  publish 时复制一份 fan-out。
- 模块级单例由 ``get_event_bus()`` 懒加载；``REDIS_URL`` 为空 / ``memory://``
  / 解析失败时退化为内存实现，避免本地开发卡住。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Protocol

from redis import asyncio as aioredis

from app.core.config import get_settings

_logger = logging.getLogger(__name__)


def build_event(event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """统一事件 schema：``{type, payload, ts}``。

    ``ts`` 用 ISO 8601 UTC，前端可直接 ``new Date(ts)``。``payload`` 可为空，
    心跳事件由 SSE 层另外发，不走 publish。
    """
    return {
        "type": event_type,
        "payload": payload or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


class EventBus(Protocol):
    async def publish(self, channel: str, event: dict[str, Any]) -> None: ...

    async def subscribe(self, channel: str) -> Subscription: ...

    async def aclose(self) -> None: ...


class Subscription(Protocol):
    """订阅句柄。

    使用范式：

    .. code-block:: python

       sub = await bus.subscribe("project:x")
       try:
           async for event in sub:
               ...
       finally:
           await sub.aclose()

    与"async generator 风格"相比，``subscribe`` 是个 awaitable，在返回前
    一定已经完成 enqueue/SUBSCRIBE，避免 publish 与订阅之间的 race window。
    """

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]: ...

    async def aclose(self) -> None: ...


class _InMemorySubscription:
    def __init__(self, bus: InMemoryEventBus, channel: str, queue: asyncio.Queue) -> None:
        self._bus = bus
        self._channel = channel
        self._queue = queue
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        try:
            while not self._closed:
                event = await self._queue.get()
                if event is _SENTINEL:
                    break
                yield event
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        async with self._bus._lock:
            subs = self._bus._subscribers.get(self._channel)
            if subs is not None:
                subs.discard(self._queue)
                if not subs:
                    self._bus._subscribers.pop(self._channel, None)


_SENTINEL: dict[str, Any] = {"__sentinel__": True}


class InMemoryEventBus:
    """单进程兜底实现。

    每个 channel 一个 ``set[asyncio.Queue]``；publish 时把 event 复制到所有队列。
    Queue 容量有限以防订阅端不消费导致内存膨胀；溢出时丢弃最旧的事件，写入
    debug 日志（任务状态推送可丢，不应阻塞 mark_job_status）。
    """

    def __init__(self, queue_maxsize: int = 256) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(channel, ()))
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # 丢弃最旧的一条以腾位置（best-effort，不阻塞 publisher）
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except Exception:  # noqa: BLE001
                    _logger.debug("in_memory_event_bus drop event channel=%s", channel)

    async def subscribe(self, channel: str) -> Subscription:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_maxsize)
        async with self._lock:
            self._subscribers.setdefault(channel, set()).add(queue)
        return _InMemorySubscription(self, channel, queue)

    async def aclose(self) -> None:
        async with self._lock:
            self._subscribers.clear()


class _RedisSubscription:
    def __init__(self, pubsub, channel: str) -> None:
        self._pubsub = pubsub
        self._channel = channel
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        import json

        try:
            async for message in self._pubsub.listen():
                if self._closed:
                    break
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if data is None:
                    continue
                try:
                    yield json.loads(data) if isinstance(data, str) else json.loads(
                        data.decode("utf-8")
                    )
                except (ValueError, UnicodeDecodeError):
                    _logger.debug(
                        "redis_event_bus drop malformed message channel=%s", self._channel
                    )
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._pubsub.unsubscribe(self._channel)
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass


class RedisEventBus:
    """基于 Redis pub/sub。

    - 用 ``redis.asyncio.Redis.from_url`` 建立一个共享连接做 publish；
      消息以 JSON 序列化。
    - 每个 ``subscribe`` 调用新开 ``PubSub`` 实例（pub/sub 在 redis-py 里
      与普通连接是隔离的）；``subscribe`` 完成 SUBSCRIBE 后再返回，
      调用方拿到的 ``Subscription`` 可以立即被 publish。
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = aioredis.from_url(redis_url, decode_responses=True)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        import json

        try:
            await self._client.publish(channel, json.dumps(event, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            # publish 不能阻断业务（mark_job_status / character_revision 等）
            _logger.exception("redis_event_bus publish failed channel=%s", channel)

    async def subscribe(self, channel: str) -> Subscription:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        return _RedisSubscription(pubsub, channel)

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception:  # noqa: BLE001
            pass


_bus: EventBus | None = None
_bus_lock = asyncio.Lock()


def _build_bus_from_settings() -> EventBus:
    settings = get_settings()
    url = (settings.redis_url or "").strip()
    if not url or url.startswith("memory://"):
        _logger.info("event_bus: using in-memory implementation")
        return InMemoryEventBus()
    if not url.startswith("redis://") and not url.startswith("rediss://"):
        _logger.warning("event_bus: unrecognized REDIS_URL=%r, falling back to in-memory", url)
        return InMemoryEventBus()
    try:
        bus = RedisEventBus(url)
        _logger.info("event_bus: using redis pub/sub at %s", url)
        return bus
    except Exception:  # noqa: BLE001
        _logger.exception("event_bus: failed to init redis bus, falling back to in-memory")
        return InMemoryEventBus()


def get_event_bus() -> EventBus:
    """惰性初始化 + 进程内单例。

    第一次 publish/subscribe 时构造；同步路径（@activity.defn 内）也能用。
    """
    global _bus
    if _bus is None:
        _bus = _build_bus_from_settings()
    return _bus


async def reset_event_bus() -> None:
    """测试用：清空当前单例。"""
    global _bus
    async with _bus_lock:
        if _bus is not None:
            try:
                await _bus.aclose()
            except Exception:  # noqa: BLE001
                pass
        _bus = None


def publish_event_fire_and_forget(channel: str, event: dict[str, Any]) -> None:
    """同步调用方（无 await 上下文）使用的发布入口。

    在 ``mark_job_status`` 这类 activity 内部使用：activity 函数本身是
    async 的，可以 ``await get_event_bus().publish(...)``；但为了让 publish
    完全脱离 DB session 生命周期（避免拖慢 commit），用 ``create_task``
    异步触发。该任务被显式忽略，异常通过 ``add_done_callback`` 记录日志。
    """
    bus = get_event_bus()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有 running loop（极端兜底）：放弃推送
        _logger.debug("publish_event_fire_and_forget: no running loop, drop channel=%s", channel)
        return

    task = loop.create_task(bus.publish(channel, event))

    def _log_err(t: asyncio.Task[Any]) -> None:
        try:
            t.result()
        except Exception:  # noqa: BLE001
            _logger.exception("event_bus background publish failed channel=%s", channel)

    task.add_done_callback(_log_err)
