"""认证流程测试：register / login / refresh / me / 跨租户拒绝。"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.passwords import hash_password
from app.models.user import User
from app.services.auth.service import auth_service


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
    assert data["user"]["platform_role"] == "super_admin"


@pytest.mark.asyncio
async def test_only_first_registered_user_becomes_super_admin(client):
    first = await client.post(
        "/api/v1/auth/register",
        json={"email": "first@example.com", "password": "password123", "display_name": "First"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["user"]["platform_role"] == "super_admin"

    second = await client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "password": "password123", "display_name": "Second"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["user"]["platform_role"] == "user"


@pytest.mark.asyncio
async def test_demo_writer_seed_does_not_block_first_real_registered_super_admin(
    client, db_session
):
    await db_session.execute(
        text(
            """
            INSERT INTO users
              (id, email, password_hash, display_name, status, is_platform_staff, platform_role)
            VALUES
              (:writer_id, :writer_email, :writer_hash, '演示作者', 'active', false, 'user')
            """
        ),
        {
            "writer_id": "user_writer",
            "writer_email": "writer@example.com",
            "writer_hash": hash_password("writer123456"),
        },
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "password123", "display_name": "Owner"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["platform_role"] == "super_admin"


@pytest.mark.asyncio
async def test_startup_promotes_existing_first_real_user_to_super_admin(db_session):
    user = User(
        id="user_real",
        email="real@example.com",
        password_hash=hash_password("password123"),
        display_name="Real",
        status="active",
        platform_role="user",
        is_platform_staff=False,
    )
    db_session.add(user)
    await db_session.commit()

    await auth_service.ensure_bootstrap_super_admin(db_session)

    await db_session.refresh(user)
    assert user.platform_role == "super_admin"
    assert user.is_platform_staff is True


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


@pytest.mark.asyncio
async def test_register_persists_when_invitation_table_is_missing(client, db_session):
    await db_session.execute(text("DROP TABLE organization_invitations"))
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dora@example.com", "password": "password123", "display_name": "Dora"},
    )
    assert response.status_code == 201, response.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "dora@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
