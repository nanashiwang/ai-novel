"""Sprint 14-C4：风格样本 CRUD 与 ContextBuilder 召回段。"""
from __future__ import annotations

import pytest

from app.models import Chapter, NovelSpec, Project, Scene, StyleSample
from app.models.common import new_id


async def _register_with_project(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "作者"},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    project = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "风格样本测试项目",
            "premise": "为了测试风格召回",
            "genre": "现代",
            "style": "克制冷峻",
            "target_reader": "类型小说读者",
        },
    )
    assert project.status_code == 201, project.text
    return token, project.json()["id"]


@pytest.mark.asyncio
async def test_style_sample_crud_flow(client, db_session):
    token, project_id = await _register_with_project(client, "style@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 初始列表应为空
    res = await client.get(f"/api/v1/projects/{project_id}/style-samples", headers=headers)
    assert res.status_code == 200
    assert res.json() == []

    # 创建一条
    res = await client.post(
        f"/api/v1/projects/{project_id}/style-samples",
        headers=headers,
        json={
            "label": "开篇段落",
            "content": "雾气压低了城市，灯光在水面上摔成碎片。",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    sample_id = body["id"]
    assert body["label"] == "开篇段落"
    assert body["project_id"] == project_id
    assert body["content"].startswith("雾气")
    assert "embedding" not in body  # 不暴露 embedding

    # 后端真实持久化 embedding（非空向量）
    row = await db_session.get(StyleSample, sample_id)
    assert row is not None
    assert row.embedding is not None
    assert isinstance(row.embedding, list) and len(row.embedding) == 1536

    # 列表能取到刚创建的样本
    res = await client.get(f"/api/v1/projects/{project_id}/style-samples", headers=headers)
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["id"] == sample_id

    # 删除
    res = await client.delete(
        f"/api/v1/projects/{project_id}/style-samples/{sample_id}",
        headers=headers,
    )
    assert res.status_code == 204

    # 删除后列表回空
    res = await client.get(f"/api/v1/projects/{project_id}/style-samples", headers=headers)
    assert res.json() == []


@pytest.mark.asyncio
async def test_style_sample_delete_not_found(client):
    token, project_id = await _register_with_project(client, "style2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.delete(
        f"/api/v1/projects/{project_id}/style-samples/style_unknown",
        headers=headers,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "style_sample_not_found"


@pytest.mark.asyncio
async def test_context_builder_injects_style_samples(db_session):
    """有样本时 style_samples 段非空，并出现在 prompt；无样本时段为空且 prompt 跳过。"""
    from app.services.context_builder import ContextBuilder
    from app.services.embedding import embedding_service

    builder = ContextBuilder(total_budget=4000)
    org_id = new_id("org")
    project_id = new_id("project")
    project = Project(
        id=project_id,
        organization_id=org_id,
        created_by="user_x",
        title="风格测试",
        genre="现代",
        target_word_count=20000,
        target_chapter_count=3,
        language="zh-CN",
        style="冷峻",
        status="outlined",
        cover_url="",
        tags=[],
        target_reader="—",
    )
    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="风格样本召回测试前提",
        theme="测试主题",
        genre="现代",
        tone="冷静",
        target_reader="—",
        narrative_pov="第三人称",
        style_guide="画面优先",
        constraints=["保持视角一致"],
        continuity_rules=[],
    )
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="第一章",
        summary="开局",
        goal="建立悬念",
        conflict="迷雾笼罩",
        ending_hook="揭开一角",
        status="planned",
    )
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="登场",
        location="码头",
        characters=["顾眠"],
        goal="建立基调",
        conflict="迷雾笼罩",
        emotion_start="平静",
        emotion_end="警觉",
        reveal="档案员的暗号",
        hook="水面浮出一只手",
        time_marker="雨夜",
        status="planned",
    )
    db_session.add_all([project, spec, chapter, scene])
    await db_session.commit()

    # 1) 没有任何 style sample 时：段为空，但 segments 里依然存在该段
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    style_seg = next(s for s in ctx.segments if s.label == "style_samples")
    assert style_seg.content == ""
    assert style_seg.trusted is True
    assert "[style_samples]" not in ctx.to_prompt()
    # 顺序：style_samples 在 characters 之后（合并后中间还有 character_actions）
    labels = [s.label for s in ctx.segments]
    assert labels.index("style_samples") > labels.index("characters")
    assert labels.index("style_samples") < labels.index("world_rules")

    # 2) 插入两条样本后再 build：内容含 label，并出现在 prompt
    embedding = await embedding_service.embed("码头登场 迷雾笼罩")
    db_session.add_all(
        [
            StyleSample(
                id=new_id("style"),
                organization_id=org_id,
                project_id=project_id,
                label="码头段落",
                content="雾气压低了码头，灯光在水面上摔成碎片。",
                embedding=embedding,
                created_by="user_x",
            ),
            StyleSample(
                id=new_id("style"),
                organization_id=org_id,
                project_id=project_id,
                label="审讯段落",
                content="档案员把回执推过桌面，他的指甲缝里还藏着烟灰。",
                embedding=embedding,
                created_by="user_x",
            ),
        ]
    )
    await db_session.commit()

    ctx2 = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    style_seg2 = next(s for s in ctx2.segments if s.label == "style_samples")
    assert "码头段落" in style_seg2.content or "审讯段落" in style_seg2.content
    prompt = ctx2.to_prompt()
    assert "[style_samples]" in prompt


@pytest.mark.asyncio
async def test_segment_budget_sums_to_one():
    """预算分布应当严格 sum=1。"""
    from app.services.context_builder.service import _SEGMENT_BUDGET_PCT

    total = sum(_SEGMENT_BUDGET_PCT.values())
    assert abs(total - 1.0) < 1e-6, total
    # 新段必须存在且预算为 0.06
    assert _SEGMENT_BUDGET_PCT["style_samples"] == pytest.approx(0.06)
    # memory_recall 合并 C2+C4+C5+E3 后落到 0.06（chapter_arc 又挤了 0.02 出来）
    assert _SEGMENT_BUDGET_PCT["memory_recall"] == pytest.approx(0.06)
