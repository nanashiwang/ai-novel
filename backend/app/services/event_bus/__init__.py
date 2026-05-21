"""事件总线服务。

向前端推送任务状态变化等异步事件。两种实现：

- ``RedisEventBus``：基于 Redis pub/sub，跨 worker / 跨进程可用。
- ``InMemoryEventBus``：基于 ``asyncio.Queue``，单进程兜底，
  本地无 Redis / 测试环境 ``REDIS_URL=memory://`` 时使用。

入口 :func:`get_event_bus` 会根据 ``REDIS_URL`` 自动选择实现，
所有发布/订阅都通过该单例完成。
"""
from __future__ import annotations

from .bus import (
    EventBus,
    InMemoryEventBus,
    RedisEventBus,
    Subscription,
    build_event,
    get_event_bus,
    publish_event_fire_and_forget,
    reset_event_bus,
)

__all__ = [
    "EventBus",
    "InMemoryEventBus",
    "RedisEventBus",
    "Subscription",
    "build_event",
    "get_event_bus",
    "publish_event_fire_and_forget",
    "reset_event_bus",
]
