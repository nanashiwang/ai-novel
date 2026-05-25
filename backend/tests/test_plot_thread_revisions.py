"""PlotThreadRevision 流程测试。

镜像 test_world_revisions.py，重点覆盖剧情线 status 变更（open → closed）以及
description 精细化两种典型场景。
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import PlotThread, PlotThreadRevision
from app.services.plot_thread_tracker.extract import (
    extract_plot_thread_changes_from_scene,
)


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
            "title": "剧情线演进项目",
            "premise": "档案员追查记忆失窃案。",
            "genre": "悬疑",
            "style": "克制",
            "target_reader": "成人读者",
        },
    )
    assert project.status_code in (200, 201), project.text
    return token, org_id, project.json()["id"]


async def _create_plot_thread(client, token: str, project_id: str, **fields) -> dict:
    payload = {
        "title": "记忆失窃案",
        "thread_type": "main",
        "description": "主角追查家人记忆消失",
        "status": "open",
        **fields,
    }
    res = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_user_edit_creates_applied_revision_for_plot_thread(client, db_session):
    """PATCH 剧情线 → status 字段变化产生 applied revision；二次编辑 supersede 第一条。"""
    token, _, project_id = await _register_with_project(client, "thread1@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    thread = await _create_plot_thread(client, token, project_id)

    # 第一次 PATCH：关闭剧情线
    res = await client.patch(
        f"/api/v1/projects/{project_id}/plot-threads/{thread['id']}",
        headers=headers,
        json={"status": "closed"},
    )
    assert res.status_code == 200, res.text
    db_session.expire_all()
    revs = (
        (await db_session.execute(select(PlotThreadRevision))).scalars().all()
    )
    applied = [r for r in revs if r.status == "applied" and r.field == "status"]
    assert len(applied) == 1
    assert applied[0].new_value == "closed"
    assert applied[0].source == "user_edit"

    # 第二次 PATCH：把 status 改回 paused
    res = await client.patch(
        f"/api/v1/projects/{project_id}/plot-threads/{thread['id']}",
        headers=headers,
        json={"status": "paused"},
    )
    assert res.status_code == 200, res.text
    db_session.expire_all()
    revs2 = (
        (await db_session.execute(select(PlotThreadRevision))).scalars().all()
    )
    applied2 = [r for r in revs2 if r.status == "applied" and r.field == "status"]
    superseded2 = [r for r in revs2 if r.status == "superseded" and r.field == "status"]
    assert len(applied2) == 1
    assert applied2[0].new_value == "paused"
    assert len(superseded2) == 1
    assert superseded2[0].new_value == "closed"


@pytest.mark.asyncio
async def test_ai_inferred_pending_apply_for_plot_thread(client, db_engine):
    """AI 推演 → pending revision；apply 后 thread.status 落地。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "thread2@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    thread = await _create_plot_thread(client, token, project_id)

    from app.services.plot_thread_tracker import record_ai_inferred

    async with Session() as session:
        row = await session.get(PlotThread, thread["id"])
        rev = await record_ai_inferred(
            session,
            organization_id=org_id,
            project_id=project_id,
            item=row,
            field="status",
            new_value="closed",
            reason="本场景主角揭穿罪犯，剧情线落幕",
            scene_id=None,
        )
        await session.commit()
        rev_id = rev.id

    # pending-count 应为 1
    count = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads/pending-count",
        headers=headers,
    )
    assert count.status_code == 200
    body = count.json()
    assert body["total"] == 1
    assert body["by_item"].get(thread["id"]) == 1

    # apply
    apply_res = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads/{thread['id']}/revisions/{rev_id}/apply",
        headers=headers,
    )
    assert apply_res.status_code == 200
    assert apply_res.json()["status"] == "applied"

    threads = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads", headers=headers
    )
    target = next(row for row in threads.json() if row["id"] == thread["id"])
    assert target["status"] == "closed"

    # pending-count 归零
    count2 = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads/pending-count",
        headers=headers,
    )
    assert count2.json()["total"] == 0


@pytest.mark.asyncio
async def test_reject_keeps_thread_untouched(client, db_engine):
    """reject pending → status 留在 rejected；plot_thread 字段保持现状。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "thread3@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    thread = await _create_plot_thread(client, token, project_id)

    from app.services.plot_thread_tracker import record_ai_inferred

    async with Session() as session:
        row = await session.get(PlotThread, thread["id"])
        rev = await record_ai_inferred(
            session,
            organization_id=org_id,
            project_id=project_id,
            item=row,
            field="description",
            new_value="AI 误判：剧情线已关闭",
            reason="模型误读",
            scene_id=None,
        )
        await session.commit()
        rev_id = rev.id

    res = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads/{thread['id']}/revisions/{rev_id}/reject",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    # description 保持不变
    threads = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads", headers=headers
    )
    target = next(row for row in threads.json() if row["id"] == thread["id"])
    assert target["description"] == "主角追查家人记忆消失"


@pytest.mark.asyncio
async def test_extract_plot_thread_changes_from_scene_writes_pending(client, db_engine):
    """模拟 extract.py：mock 模型返回一条 status 变化 → 走 record_ai_inferred → pending。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "thread4@example.com"
    )
    from sqlalchemy import select as _sel

    from app.models import User

    async with Session() as session:
        user = (
            await session.execute(
                _sel(User).where(User.email == "thread4@example.com")
            )
        ).scalar_one()
        user_id = user.id

    thread = await _create_plot_thread(client, token, project_id)

    from app.models import Chapter, DraftVersion, Scene
    from app.models.common import new_id

    async with Session() as session:
        chapter = Chapter(
            id=new_id("chapter"),
            organization_id=org_id,
            project_id=project_id,
            volume_id=None,
            chapter_index=5,
            title="第五章 真相",
            summary="主角揭穿罪犯",
            goal="揭穿真相",
            conflict="对峙",
            ending_hook="罪犯被捕",
            status="planned",
        )
        session.add(chapter)
        await session.flush()
        scene = Scene(
            id=new_id("scene"),
            organization_id=org_id,
            project_id=project_id,
            chapter_id=chapter.id,
            scene_index=3,
            title="档案室对峙",
            time_marker="深夜",
            location="档案室",
            characters=["林澈", "苏怀玦"],
            goal="揭穿罪犯",
            conflict="正面对峙",
            emotion_start="紧张",
            emotion_end="决断",
            reveal="罪犯身份",
            hook="档案被销毁",
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
                "林澈在档案室揭穿了苏怀玦窃取家人记忆的事实，"
                "记忆失窃案至此告一段落——主线剧情线正式闭合。"
            ),
            word_count=70,
            status="draft",
            parent_version_id=None,
            created_by=user_id,
        )
        session.add(draft)
        await session.commit()
        scene_id = scene.id
        chapter_id = chapter.id
        draft_id = draft.id

    from app.services.model_gateway.service import model_gateway

    class _StubProvider:
        async def complete_json(self, **kwargs):
            return {
                "changes": [
                    {
                        "item_id": thread["id"],
                        "field": "status",
                        "new_value": "closed",
                        "reason": "主角揭穿，剧情线正式落幕",
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
            result = await extract_plot_thread_changes_from_scene(
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

    headers = {"Authorization": f"Bearer {token}"}
    count = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads/pending-count",
        headers=headers,
    )
    assert count.json()["total"] == 1
