"""ContextBuilder world_actions / plot_actions 段集成测试（Sprint 13-B2）。

覆盖：
- build_for_scene_writing 注入 world_actions / plot_actions 两段
- 仅 status='applied' 的 revision 被召回；pending/rejected 不进段
- 字段渲染：name · field：old → new（reason）
- 无 revision 时段为空，不输出标题，整段被 to_prompt() 跳过
"""
from __future__ import annotations

from datetime import datetime, timezone

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
        json={"title": "B2 召回测试", "genre": "奇幻"},
    )
    assert project_res.status_code in (200, 201), project_res.text
    return token, project_res.json()["id"]


@pytest.mark.asyncio
async def test_context_builder_world_and_plot_actions_segments(client, db_session):
    """两段联合验证：world_actions 与 plot_actions 都按 applied + 时间倒序召回。"""
    from sqlalchemy import select

    from app.models.chapter import Chapter
    from app.models.common import new_id
    from app.models.plot_thread import PlotThread
    from app.models.plot_thread_revision import PlotThreadRevision
    from app.models.project import NovelSpec, Project
    from app.models.scene import Scene
    from app.models.world_item import WorldItem
    from app.models.world_item_revision import WorldItemRevision
    from app.services.context_builder import ContextBuilder

    token, project_id = await _register_with_project(client, "b2-recall@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org_id = me["organization_id"]

    project = (
        await db_session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one()

    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="测试", theme="测试", genre="奇幻", tone="紧张",
        target_reader="—", narrative_pov="第三人称", style_guide="—",
        constraints=[], continuity_rules=[],
    )
    db_session.add(spec)

    # 世界观条目 + 一条 applied 修订 + 一条 pending（不应被召回）
    city = WorldItem(
        id=new_id("world"), organization_id=org_id, project_id=project_id,
        name="主城雾都", type="location", description="阴雨之都", is_hard_rule=False,
    )
    rev_applied = WorldItemRevision(
        id=new_id("wir"), organization_id=org_id, project_id=project_id,
        item_id=city.id, field="description",
        old_value="阴雨之都", new_value="被妖兽攻陷的废墟",
        reason="第三章末爆发", source="user_edit", status="applied",
        applied_at=datetime.now(timezone.utc),
    )
    rev_pending = WorldItemRevision(
        id=new_id("wir"), organization_id=org_id, project_id=project_id,
        item_id=city.id, field="description",
        old_value="被妖兽攻陷的废墟", new_value="重建后的钢铁都市",
        reason="尚未确认", source="ai_inferred", status="pending",
    )

    # 剧情线 + 一条 applied 修订
    thread = PlotThread(
        id=new_id("pth"), organization_id=org_id, project_id=project_id,
        title="封印结界破裂", thread_type="main", description="主线",
        status="open",
    )
    pthr_applied = PlotThreadRevision(
        id=new_id("ptr"), organization_id=org_id, project_id=project_id,
        item_id=thread.id, field="status",
        old_value="dormant", new_value="active",
        reason="主角接触封印石", source="user_edit", status="applied",
        applied_at=datetime.now(timezone.utc),
    )

    # scene 准备（用于 build_for_scene_writing 入参）
    chapter = Chapter(
        id=new_id("chapter"), organization_id=org_id, project_id=project_id,
        volume_id=None, chapter_index=1, title="开端", summary="", goal="",
        conflict="", ending_hook="", status="drafted",
    )
    scene = Scene(
        id=new_id("scene"), organization_id=org_id, project_id=project_id,
        chapter_id=chapter.id, scene_index=1, title="夜雨", time_marker="",
        location="", characters=[], goal="", conflict="",
        emotion_start="", emotion_end="", reveal="", hook="", status="planned",
    )
    db_session.add_all([city, rev_applied, rev_pending, thread, pthr_applied, chapter, scene])
    await db_session.commit()

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    labels = [s.label for s in ctx.segments]
    assert "world_actions" in labels
    assert "plot_actions" in labels

    world_seg = next(s for s in ctx.segments if s.label == "world_actions")
    plot_seg = next(s for s in ctx.segments if s.label == "plot_actions")
    assert world_seg.trusted is True
    assert plot_seg.trusted is True

    # applied 命中，pending 不应出现
    assert "主城雾都" in world_seg.content
    assert "被妖兽攻陷的废墟" in world_seg.content
    assert "重建后的钢铁都市" not in world_seg.content  # pending 被排除

    assert "封印结界破裂" in plot_seg.content
    assert "active" in plot_seg.content
    assert "[main]" in plot_seg.content


@pytest.mark.asyncio
async def test_context_builder_actions_empty_when_no_revisions(client, db_session):
    """空数据时两段都为空，to_prompt() 跳过整段，不输出标题。"""
    from sqlalchemy import select

    from app.models.chapter import Chapter
    from app.models.common import new_id
    from app.models.project import NovelSpec, Project
    from app.models.scene import Scene
    from app.services.context_builder import ContextBuilder

    token, project_id = await _register_with_project(client, "b2-empty@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org_id = me["organization_id"]

    project = (
        await db_session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one()
    spec = NovelSpec(
        id=new_id("spec"), organization_id=org_id, project_id=project_id,
        premise="", theme="", genre="", tone="", target_reader="",
        narrative_pov="", style_guide="", constraints=[], continuity_rules=[],
    )
    chapter = Chapter(
        id=new_id("chapter"), organization_id=org_id, project_id=project_id,
        volume_id=None, chapter_index=1, title="t", summary="", goal="",
        conflict="", ending_hook="", status="planned",
    )
    scene = Scene(
        id=new_id("scene"), organization_id=org_id, project_id=project_id,
        chapter_id=chapter.id, scene_index=1, title="s", time_marker="",
        location="", characters=[], goal="", conflict="",
        emotion_start="", emotion_end="", reveal="", hook="", status="planned",
    )
    db_session.add_all([spec, chapter, scene])
    await db_session.commit()

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    world_seg = next(s for s in ctx.segments if s.label == "world_actions")
    plot_seg = next(s for s in ctx.segments if s.label == "plot_actions")
    assert world_seg.content == ""
    assert plot_seg.content == ""
    prompt = ctx.to_prompt()
    assert "world_actions" not in prompt
    assert "plot_actions" not in prompt
