"""人物字段版本链端到端测试。

覆盖：
- 创建 character 后修改：每个变化字段产 source='user_edit' status='applied' revision
- 应用 / 驳回 / 回滚 pending revision
- 同字段多次修改：旧 applied 标 superseded
- pending 计数聚合
"""
from __future__ import annotations

import pytest


async def _register_with_project(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    project_res = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "动态人物测试", "genre": "悬疑"},
    )
    assert project_res.status_code in (200, 201), project_res.text
    return token, project_res.json()["id"]


async def _create_character(client, token, project_id, **overrides) -> dict:
    payload = {
        "name": "林秋",
        "role": "protagonist",
        "description": "失忆的档案管理员",
        "personality": "内敛",
        "motivation": "找回记忆",
        "secret": "",
        "arc": "",
        "relationships": {},
        "current_state": {},
    }
    payload.update(overrides)
    res = await client.post(
        f"/api/v1/projects/{project_id}/characters",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_character_update_produces_applied_revisions(client):
    """编辑 character 字段 → 每个变化字段生成 source='user_edit' status='applied' 记录。"""
    token, project_id = await _register_with_project(client, "char-rev-1@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 修改 motivation 和 personality
    patch = await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={
            **character,
            "motivation": "找回记忆并查清姐姐死因",
            "personality": "内敛且执着",
        },
    )
    assert patch.status_code == 200

    # 列出 revisions
    rev_res = await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
    )
    assert rev_res.status_code == 200
    revisions = rev_res.json()
    # 两个字段变化 → 两条 revision，都是 user_edit + applied
    assert len(revisions) == 2
    assert all(r["source"] == "user_edit" for r in revisions)
    assert all(r["status"] == "applied" for r in revisions)
    fields = {r["field"] for r in revisions}
    assert fields == {"motivation", "personality"}


@pytest.mark.asyncio
async def test_character_update_same_field_supersedes_old(client):
    """同字段二次修改：旧 applied 应标 superseded，新 applied 生效。"""
    token, project_id = await _register_with_project(client, "char-rev-2@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    for new_motivation in ("v1", "v2"):
        await client.patch(
            f"/api/v1/projects/{project_id}/characters/{character['id']}",
            headers=headers,
            json={**character, "motivation": new_motivation},
        )

    revs = (await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
    )).json()
    motivation_revs = [r for r in revs if r["field"] == "motivation"]
    # 应有 2 条；其中 1 条 applied（最新 v2），1 条 superseded（旧 v1）
    assert len(motivation_revs) == 2
    statuses = sorted(r["status"] for r in motivation_revs)
    assert statuses == ["applied", "superseded"]
    applied = next(r for r in motivation_revs if r["status"] == "applied")
    assert applied["new_value"] == "v2"


@pytest.mark.asyncio
async def test_character_revision_rollback(client):
    """把历史 revision 重新 apply：character 字段回到目标值，新增一条 user_edit applied 记录。"""
    token, project_id = await _register_with_project(client, "char-rev-3@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 两次修改：v1 → v2
    await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={**character, "motivation": "v1"},
    )
    await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={**character, "motivation": "v2"},
    )

    # 找到第一条（v1）revision
    revs = (await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
    )).json()
    v1_rev = next(r for r in revs if r["new_value"] == "v1")

    # 回滚到 v1
    rollback = await client.post(
        (
            f"/api/v1/projects/{project_id}/characters/{character['id']}"
            f"/revisions/{v1_rev['id']}/rollback"
        ),
        headers=headers,
    )
    assert rollback.status_code == 200, rollback.text
    rollback_rev = rollback.json()
    assert rollback_rev["new_value"] == "v1"
    assert rollback_rev["status"] == "applied"
    assert "回滚" in rollback_rev["reason"]

    # character 当前值应为 v1
    char_res = await client.get(
        f"/api/v1/projects/{project_id}/characters",
        headers=headers,
    )
    current = next(c for c in char_res.json() if c["id"] == character["id"])
    assert current["motivation"] == "v1"


@pytest.mark.asyncio
async def test_character_revisions_pending_count(client, db_session):
    """pending-count 聚合：直接造一条 pending revision，确认 count 为 1。"""
    from app.models.character_revision import CharacterRevision
    from app.models.common import new_id

    token, project_id = await _register_with_project(client, "char-rev-4@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 直接造 pending 记录（模拟 AI 推演产出，Phase B 才有真实链路）
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    db_session.add(
        CharacterRevision(
            id=new_id("char_rev"),
            organization_id=me["organization_id"],
            project_id=project_id,
            character_id=character["id"],
            field="current_state",
            old_value={},
            new_value={"abilities": ["识别加密签名"]},
            reason="第 10 章主角破解了一份七年前的加密文件",
            source="ai_inferred",
            scene_id=None,
            status="pending",
            created_by=me["id"],
        )
    )
    await db_session.commit()

    count_res = await client.get(
        f"/api/v1/projects/{project_id}/character-revisions/pending-count",
        headers=headers,
    )
    assert count_res.status_code == 200
    counts = count_res.json()
    assert {"character_id": character["id"], "pending_count": 1} in counts
