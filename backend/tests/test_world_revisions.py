"""WorldItemRevision 流程测试。

覆盖 Sprint 12-C Phase B 的端到端能力：
- 用户手动编辑 → applied revision；旧 applied 自动 superseded
- AI 推演（mock model_gateway）→ pending revision
- apply pending → 同字段旧 applied 被 superseded、字段被写入
- pending_count 端点按 item_id 聚合
- reject + rollback 流程
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import WorldItem, WorldItemRevision
from app.services.world_tracker.extract import extract_world_changes_from_scene


async def _register_with_project(client, email: str) -> tuple[str, str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "作者"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    token = body["access_token"]
    org_id = body["user"]["organization_id"]
    project = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "雾城世界观演进",
            "premise": "档案员发现记忆交易。",
            "genre": "悬疑幻想",
            "style": "克制",
            "target_reader": "成人读者",
        },
    )
    assert project.status_code in (200, 201), project.text
    return token, org_id, project.json()["id"]


async def _create_world_item(client, token: str, project_id: str, **fields) -> dict:
    payload = {
        "type": "rule",
        "name": "记忆等价交换",
        "description": "任何记忆交易都必须付出等量情绪代价。",
        "importance": "high",
        "is_hard_rule": True,
        **fields,
    }
    res = await client.post(
        f"/api/v1/projects/{project_id}/world-items",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_user_edit_creates_applied_revision_and_supersedes_old(
    client, db_session
):
    """手动 PATCH 字段 → 写一条 applied revision；再 PATCH → 旧 applied 自动 superseded。"""
    token, _, project_id = await _register_with_project(client, "world1@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    item = await _create_world_item(client, token, project_id)

    # 第一次 PATCH：description 变化
    res = await client.patch(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}",
        headers=headers,
        json={
            "type": item["type"],
            "name": item["name"],
            "description": "记忆交易需付出等量情绪代价，且代价不可逆。",
            "importance": item.get("importance", "high"),
            "is_hard_rule": item.get("is_hard_rule", True),
        },
    )
    assert res.status_code == 200, res.text
    db_session.expire_all()
    revs = (
        (await db_session.execute(select(WorldItemRevision))).scalars().all()
    )
    applied = [r for r in revs if r.status == "applied"]
    assert len(applied) == 1
    assert applied[0].field == "description"
    assert applied[0].source == "user_edit"

    # 第二次 PATCH：再改 description
    res = await client.patch(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}",
        headers=headers,
        json={
            "type": item["type"],
            "name": item["name"],
            "description": "记忆交易需付出等量情绪代价，且代价会损耗灵魂寿命。",
            "importance": item.get("importance", "high"),
            "is_hard_rule": item.get("is_hard_rule", True),
        },
    )
    assert res.status_code == 200, res.text
    db_session.expire_all()
    revs2 = (
        (await db_session.execute(select(WorldItemRevision))).scalars().all()
    )
    applied2 = [r for r in revs2 if r.status == "applied" and r.field == "description"]
    superseded2 = [
        r for r in revs2 if r.status == "superseded" and r.field == "description"
    ]
    assert len(applied2) == 1
    assert len(superseded2) == 1

    # history 端点应可读取
    listing = await client.get(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}/revisions",
        headers=headers,
    )
    assert listing.status_code == 200
    assert len(listing.json()) >= 2


@pytest.mark.asyncio
async def test_ai_inferred_creates_pending_revision_and_can_be_applied(
    client, db_session, db_engine
):
    """模拟 extract.py 反推路径：写 pending revision，apply 后字段生效并 supersede 旧 applied。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "world2@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    item = await _create_world_item(client, token, project_id)

    # 直接调用 tracker 写一条 pending（模拟 AI 推演通过模型推断出的描述变更）
    from app.services.world_tracker import record_ai_inferred

    async with Session() as session:
        wi = await session.get(WorldItem, item["id"])
        rev = await record_ai_inferred(
            session,
            organization_id=org_id,
            project_id=project_id,
            item=wi,
            field="description",
            new_value="记忆交易需付出灵魂寿命，规则在第三章被验证。",
            reason="scene 中明确出现寿命扣除",
            scene_id=None,
        )
        await session.commit()
        revision_id = rev.id

    # pending-count 端点
    count = await client.get(
        f"/api/v1/projects/{project_id}/world-items/pending-count",
        headers=headers,
    )
    assert count.status_code == 200
    body = count.json()
    assert body["total"] == 1
    assert body["by_item"].get(item["id"]) == 1

    # apply
    apply_res = await client.post(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}/revisions/{revision_id}/apply",
        headers=headers,
    )
    assert apply_res.status_code == 200, apply_res.text
    assert apply_res.json()["status"] == "applied"

    # 字段已被写入
    items = await client.get(
        f"/api/v1/projects/{project_id}/world-items",
        headers=headers,
    )
    target = next(row for row in items.json() if row["id"] == item["id"])
    assert "灵魂寿命" in target["description"]

    # 之前那条 applied（来自 create 时不会有，但 history 上看新 applied）
    listing = await client.get(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}/revisions",
        headers=headers,
    )
    assert listing.status_code == 200
    statuses = {row["status"] for row in listing.json()}
    assert "applied" in statuses
    # pending-count 现在应为 0
    count2 = await client.get(
        f"/api/v1/projects/{project_id}/world-items/pending-count",
        headers=headers,
    )
    assert count2.json()["total"] == 0


@pytest.mark.asyncio
async def test_reject_and_rollback_flow(client, db_session, db_engine):
    """reject pending 不会改 item；rollback 把字段回到历史 revision 的 new_value。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "world3@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    item = await _create_world_item(
        client, token, project_id, description="原始描述 A"
    )

    # 用户编辑 → applied revision（A → B）
    res = await client.patch(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}",
        headers=headers,
        json={
            "type": item["type"],
            "name": item["name"],
            "description": "用户编辑后的描述 B",
            "importance": item.get("importance", "high"),
            "is_hard_rule": item.get("is_hard_rule", True),
        },
    )
    assert res.status_code == 200

    # 再编辑一次（B → C），让 B 变成 superseded，C 是当前 applied
    res = await client.patch(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}",
        headers=headers,
        json={
            "type": item["type"],
            "name": item["name"],
            "description": "用户编辑后的描述 C",
            "importance": item.get("importance", "high"),
            "is_hard_rule": item.get("is_hard_rule", True),
        },
    )
    assert res.status_code == 200

    # 写一条 pending（D），然后 reject
    from app.services.world_tracker import record_ai_inferred

    async with Session() as session:
        wi = await session.get(WorldItem, item["id"])
        rev = await record_ai_inferred(
            session,
            organization_id=org_id,
            project_id=project_id,
            item=wi,
            field="description",
            new_value="AI 推断的描述 D",
            reason="测试 reject",
            scene_id=None,
        )
        await session.commit()
        pending_id = rev.id

    reject_res = await client.post(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}/revisions/{pending_id}/reject",
        headers=headers,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    items = await client.get(
        f"/api/v1/projects/{project_id}/world-items", headers=headers
    )
    target = next(row for row in items.json() if row["id"] == item["id"])
    assert target["description"] == "用户编辑后的描述 C", "reject 不应修改 item"

    # 找到 superseded 的那条（B 版本）然后 rollback 到它
    listing = await client.get(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}/revisions",
        headers=headers,
    )
    rows = listing.json()
    superseded = [r for r in rows if r.get("status") == "superseded"]
    assert superseded, f"应有 superseded revision，可用 rollback；rows={rows}"
    rollback_target_id = superseded[0]["id"]
    rollback_target_value = superseded[0]["new_value"]

    rollback_res = await client.post(
        f"/api/v1/projects/{project_id}/world-items/{item['id']}/revisions/{rollback_target_id}/rollback",
        headers=headers,
    )
    assert rollback_res.status_code == 200, rollback_res.text

    items2 = await client.get(
        f"/api/v1/projects/{project_id}/world-items", headers=headers
    )
    target2 = next(row for row in items2.json() if row["id"] == item["id"])
    assert target2["description"] == rollback_target_value


@pytest.mark.asyncio
async def test_extract_world_changes_from_scene_writes_pending(
    client, db_engine
):
    """模拟 fire-and-forget extract 路径：mock DeterministicModelProvider 返回
    一条 world_item 字段变化 → 走 record_ai_inferred → 写 pending revision。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "world4@example.com"
    )
    # 获取 user_id 用于后续 DraftVersion 写入
    from sqlalchemy import select as _sel

    from app.models import User

    async with Session() as session:
        user = (
            await session.execute(
                _sel(User).where(User.email == "world4@example.com")
            )
        ).scalar_one()
        user_id = user.id

    item = await _create_world_item(client, token, project_id)

    # 准备 scene / chapter / draft
    from app.models import Chapter, DraftVersion, Scene
    from app.models.common import new_id

    async with Session() as session:
        chapter = Chapter(
            id=new_id("chapter"),
            organization_id=org_id,
            project_id=project_id,
            volume_id=None,
            chapter_index=1,
            title="第一章 雾起",
            summary="档案员第一次接触灰市记忆。",
            goal="揭示规则",
            conflict="无",
            ending_hook="灰市浮现",
            status="planned",
        )
        session.add(chapter)
        await session.flush()
        scene = Scene(
            id=new_id("scene"),
            organization_id=org_id,
            project_id=project_id,
            chapter_id=chapter.id,
            scene_index=1,
            title="档案馆的清晨",
            time_marker="清晨",
            location="雾城档案馆",
            characters=["林澈"],
            goal="揭开记忆交易副作用",
            conflict="规则验证",
            emotion_start="平静",
            emotion_end="震惊",
            reveal="记忆交易会损耗寿命",
            hook="档案柜深处的封缄",
            status="drafted",
        )
        session.add(scene)
        await session.flush()
        draft = DraftVersion(
            id=new_id("draft"),
            organization_id=org_id,
            project_id=project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            version_type="draft",
            content=(
                "林澈在档案馆里翻出一份契约，背面写着：每完成一次记忆交易，"
                "缔约者寿命会被悄悄取走数年——这显然是新的硬规则。"
            ),
            word_count=80,
            status="draft",
            parent_version_id=None,
            created_by=user_id,
        )
        session.add(draft)
        await session.commit()
        scene_id = scene.id
        chapter_id = chapter.id
        draft_id = draft.id

    # mock provider 返回一条 world 变化
    from app.services.model_gateway.service import model_gateway

    class _StubProvider:
        async def complete_json(self, **kwargs):
            return {
                "changes": [
                    {
                        "item_id": item["id"],
                        "field": "description",
                        "new_value": (
                            "记忆交易付出寿命代价；第一章档案室确认了规则的副作用。"
                        ),
                        "reason": "draft 中明确出现寿命损耗",
                    }
                ]
            }

        async def complete_text(self, **kwargs):
            return ""

    original_provider = model_gateway._provider
    model_gateway.set_provider(_StubProvider())
    try:
        async with Session() as session:
            chapter_row = await session.get(Chapter, chapter_id)
            scene_row = await session.get(Scene, scene_id)
            draft_row = await session.get(DraftVersion, draft_id)
            result = await extract_world_changes_from_scene(
                session,
                organization_id=org_id,
                project_id=project_id,
                job_id=None,
                chapter=chapter_row,
                scene=scene_row,
                draft=draft_row,
            )
            await session.commit()
    finally:
        model_gateway.set_provider(original_provider)

    assert result["pending_count"] == 1

    # 通过 API 验证 pending 已注入
    headers = {"Authorization": f"Bearer {token}"}
    count = await client.get(
        f"/api/v1/projects/{project_id}/world-items/pending-count",
        headers=headers,
    )
    assert count.json()["total"] == 1
