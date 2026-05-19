"""项目 CRUD + 租户隔离集成测试。"""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_create_list_get_delete_project(client):
    token, _ = await _register(client, "pa1@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/api/v1/projects",
        json={"title": "测试项目", "target_word_count": 5000, "tags": ["a", "b"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["tags"] == ["a", "b"]

    listing = await client.get("/api/v1/projects", headers=headers)
    assert listing.status_code == 200
    assert any(p["id"] == pid for p in listing.json())

    detail = await client.get(f"/api/v1/projects/{pid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["title"] == "测试项目"

    deleted = await client.delete(f"/api/v1/projects/{pid}", headers=headers)
    assert deleted.status_code == 204

    not_found = await client.get(f"/api/v1/projects/{pid}", headers=headers)
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_project_pagination(client):
    token, _ = await _register(client, "pp@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(5):
        await client.post(
            "/api/v1/projects",
            json={"title": f"项目 {i}", "target_word_count": 1000},
            headers=headers,
        )

    res = await client.get("/api/v1/projects?page=1&page_size=2", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2

    res = await client.get("/api/v1/projects?page=2&page_size=2", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2


@pytest.mark.asyncio
async def test_project_create_persists_initial_spec(client):
    token, _ = await _register(client, "spec@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/api/v1/projects",
        json={
            "title": "设定项目",
            "premise": "一个档案员发现城市记忆被买卖。",
            "genre": "都市悬疑",
            "style": "冷峻",
            "target_reader": "悬疑读者",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    spec = await client.get(f"/api/v1/projects/{pid}/spec", headers=headers)
    assert spec.status_code == 200, spec.text
    assert spec.json()["premise"] == "一个档案员发现城市记忆被买卖。"

    updated = await client.put(
        f"/api/v1/projects/{pid}/spec",
        json={"premise": "更新后的故事核心", "theme": "记忆与身份"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["theme"] == "记忆与身份"
