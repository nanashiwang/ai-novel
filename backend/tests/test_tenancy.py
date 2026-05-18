"""租户隔离测试。

确保：
- 用户 A 不能访问用户 B 组织的资源
- X-Organization-Id 与 token 中 organization_id 不匹配时拒绝（非平台管理员）
"""
from __future__ import annotations

import pytest


async def _register_and_token(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_user_cannot_access_other_org_via_header(client):
    a_token, a_org = await _register_and_token(client, "ua@example.com")
    _, b_org = await _register_and_token(client, "ub@example.com")

    # 用 A 的 token 携带 B 的组织 ID 访问 /auth/me → 403
    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {a_token}",
            "X-Organization-Id": b_org,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_can_access_own_org(client):
    a_token, a_org = await _register_and_token(client, "ux@example.com")
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {a_token}", "X-Organization-Id": a_org},
    )
    assert response.status_code == 200
    assert response.json()["organization_id"] == a_org


@pytest.mark.asyncio
async def test_projects_are_tenant_isolated(client):
    a_token, _ = await _register_and_token(client, "pa@example.com")
    b_token, _ = await _register_and_token(client, "pb@example.com")

    # A 创建项目
    created = await client.post(
        "/api/v1/projects",
        json={"title": "A 的项目", "target_word_count": 1000},
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    # B 列出项目时不应看到 A 的项目
    listing = await client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert listing.status_code == 200
    assert all(p["id"] != project_id for p in listing.json())
