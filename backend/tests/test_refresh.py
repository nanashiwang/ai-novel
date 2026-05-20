"""refresh token rotate / 黑名单 / 跨标签序列化测试。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_refresh_rotates_and_blacklists_old(client, monkeypatch):
    # 用内存集合替代 Redis 黑名单
    revoked: set[str] = set()

    async def fake_revoke(jti: str, exp):  # noqa: ANN001
        revoked.add(jti)

    async def fake_is_revoked(jti: str) -> bool:
        return jti in revoked

    from app.services.auth import token_store

    monkeypatch.setattr(token_store, "revoke_refresh_jti", fake_revoke)
    monkeypatch.setattr(token_store, "is_refresh_jti_revoked", fake_is_revoked)
    # service 模块在导入时直接引用了函数，需同步替换
    from app.services.auth import service as auth_service_mod

    monkeypatch.setattr(auth_service_mod, "revoke_refresh_jti", fake_revoke)
    monkeypatch.setattr(auth_service_mod, "is_refresh_jti_revoked", fake_is_revoked)

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "rot@example.com", "password": "password123", "display_name": "rot"},
    )
    cookies = reg.cookies
    refresh_token_1 = cookies.get("novelflow_refresh")
    assert refresh_token_1

    # 第一次 refresh：成功
    r1 = await client.post(
        "/api/v1/auth/refresh",
        cookies={"novelflow_refresh": refresh_token_1},
    )
    assert r1.status_code == 200
    new_refresh = r1.cookies.get("novelflow_refresh")
    assert new_refresh and new_refresh != refresh_token_1

    # 旧 token 已被撤销
    r2 = await client.post(
        "/api/v1/auth/refresh",
        cookies={"novelflow_refresh": refresh_token_1},
    )
    assert r2.status_code == 401
