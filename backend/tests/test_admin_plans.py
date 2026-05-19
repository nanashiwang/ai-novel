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
async def test_super_admin_can_create_and_update_plan(client):
    token = await _register(client, "plans-admin@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/api/v1/admin/plans",
        headers=headers,
        json={
            "code": "Creator",
            "name": "Creator",
            "description": "创作者套餐",
            "price_monthly": 79,
            "price_yearly": 790,
            "currency": "CNY",
            "status": "active",
            "features": [
                {
                    "feature_key": "monthly_generated_words",
                    "enabled": True,
                    "limit_value": 600000,
                    "limit_unit": "words",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["code"] == "Creator"
    assert data["price_monthly"] == 79
    assert data["features"][0]["limit_value"] == 600000

    updated = await client.put(
        f"/api/v1/admin/plans/{data['id']}",
        headers=headers,
        json={
            "code": "Creator",
            "name": "Creator Plus",
            "description": "创作者增强套餐",
            "price_monthly": 99,
            "price_yearly": None,
            "currency": "CNY",
            "status": "active",
            "features": [
                {
                    "feature_key": "monthly_generated_words",
                    "enabled": True,
                    "limit_value": 800000,
                    "limit_unit": "words",
                },
                {
                    "feature_key": "monthly_review_count",
                    "enabled": True,
                    "limit_value": 120,
                    "limit_unit": "times",
                },
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    updated_data = updated.json()
    assert updated_data["name"] == "Creator Plus"
    assert updated_data["price_yearly"] is None
    assert len(updated_data["features"]) == 2


@pytest.mark.asyncio
async def test_normal_user_cannot_create_plan(client):
    await _register(client, "plans-first@example.com")
    token = await _register(client, "plans-user@example.com")

    res = await client.post(
        "/api/v1/admin/plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "code": "Blocked",
            "name": "Blocked",
            "description": "",
            "price_monthly": 1,
            "price_yearly": None,
            "currency": "CNY",
            "status": "active",
            "features": [],
        },
    )
    assert res.status_code == 403

