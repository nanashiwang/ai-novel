"""Refresh Token 黑名单存储（Redis）。

logout / refresh 时把已使用或撤销的 refresh JTI 加入黑名单，
确保旧 token 不能再次换取 access。
"""
from __future__ import annotations

from datetime import datetime, timezone

from redis import asyncio as aioredis

from app.core.config import get_settings

_BLACKLIST_PREFIX = "auth:refresh:revoked:"
_redis_client: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def revoke_refresh_jti(jti: str, expires_at: datetime) -> None:
    """将 jti 加入黑名单，TTL 与 token 过期同步。"""
    now = datetime.now(timezone.utc)
    ttl = max(int((expires_at - now).total_seconds()), 60)
    client = _get_client()
    await client.setex(f"{_BLACKLIST_PREFIX}{jti}", ttl, "1")


async def is_refresh_jti_revoked(jti: str) -> bool:
    if not jti:
        return True
    client = _get_client()
    result = await client.get(f"{_BLACKLIST_PREFIX}{jti}")
    return result is not None
