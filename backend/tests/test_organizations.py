"""组织 / 成员 API 集成测试。"""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> tuple[str, str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    data = res.json()
    return data["access_token"], data["user"]["organization_id"], data["user"]["id"]


@pytest.mark.asyncio
async def test_list_my_organizations(client):
    token, org_id, _ = await _register(client, "om1@example.com")
    res = await client.get(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert any(o["id"] == org_id for o in res.json())


@pytest.mark.asyncio
async def test_invite_existing_user(client):
    owner_token, _, _ = await _register(client, "owner@example.com")
    _, _, _ = await _register(client, "guest@example.com")

    res = await client.post(
        "/api/v1/organizations/current/members",
        json={"email": "guest@example.com", "role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "editor"


@pytest.mark.asyncio
async def test_invite_nonexistent_user_creates_pending_invitation(client):
    owner_token, _, _ = await _register(client, "owner2@example.com")
    res = await client.post(
        "/api/v1/organizations/current/members",
        json={"email": "nobody@example.com", "role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["email"] == "nobody@example.com"
    assert res.json()["status"] == "pending"
    assert res.json()["token"]
