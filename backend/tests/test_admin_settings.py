from __future__ import annotations

import pytest


async def _register(client, email: str) -> str:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_super_admin_can_configure_model_gateway(client):
    token = await _register(client, "settings-admin@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.put(
        "/api/v1/admin/settings/model-gateway",
        headers=headers,
        json={
            "provider": "openai",
            "default_model": "gpt-4o-mini",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_api_key": "sk-test",
            "anthropic_base_url": "https://api.anthropic.com/v1",
            "anthropic_api_key": None,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ready"] is True
    assert "mode" not in data
    assert data["openai_api_key_configured"] is True
    assert "sk-test" not in res.text

    loaded = await client.get("/api/v1/admin/settings/model-gateway", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["default_model"] == "gpt-4o-mini"
    assert "sk-test" not in loaded.text


@pytest.mark.asyncio
async def test_normal_user_cannot_update_model_gateway_settings(client):
    await _register(client, "settings-first@example.com")
    token = await _register(client, "settings-user@example.com")

    res = await client.put(
        "/api/v1/admin/settings/model-gateway",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "openai",
            "default_model": "gpt-5.5",
            "openai_base_url": "https://api.openai.com/v1",
            "anthropic_base_url": "https://api.anthropic.com/v1",
        },
    )
    assert res.status_code == 403
