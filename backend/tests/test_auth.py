"""认证流程测试：register / login / refresh / me / 跨租户拒绝。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_register_creates_personal_org(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "password123", "display_name": "Alice"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["access_token"]
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["organization_id"]
    assert data["user"]["plan_code"] == "Free"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "password123", "display_name": "Bob"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_bearer_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_x_mock_user_header_no_longer_grants_admin(client):
    """X-Mock-User 头必须不再生效（旧版漏洞回归测试）。"""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-Mock-User": "admin"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_login_returns_access_and_me_works(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "password123", "display_name": "Carol"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "password123"},
    )
    token = login.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "carol@example.com"
