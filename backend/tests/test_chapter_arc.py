"""ContextBuilder chapter_arc 段集成测试（Sprint 16-E3）。

覆盖：
- chapter.scene_beats 非空时段输出本章拍点 + 当前位置标号
- scene_beats 为空时段为空、不输出标题
- chapter_arc 是 trusted 段
"""
from __future__ import annotations

import pytest

from app.models.chapter import Chapter
from app.models.common import new_id
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.services.context_builder import ContextBuilder


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
        json={"title": "E3 chapter_arc 测试", "genre": "悬疑"},
    )
    assert project_res.status_code in (200, 201), project_res.text
    return token, project_res.json()["id"]


@pytest.mark.asyncio
async def test_chapter_arc_segment_outputs_beats_and_position(client, db_session):
    from sqlalchemy import select

    token, project_id = await _register_with_project(client, "e3-beats@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org_id = me["organization_id"]

    project = (
        await db_session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one()
    spec = NovelSpec(
        id=new_id("spec"), organization_id=org_id, project_id=project_id,
        premise="", theme="", genre="悬疑", tone="", target_reader="",
        narrative_pov="", style_guide="", constraints=[], continuity_rules=[],
    )
    chapter = Chapter(
        id=new_id("chapter"), organization_id=org_id, project_id=project_id,
        volume_id=None, chapter_index=1, title="开端", summary="", goal="",
        conflict="", ending_hook="", status="planned",
        target_words=4500,
        scene_beats=[
            "开场：主角接到神秘电话",
            "推进：主角追查电话来源",
            "转折：线索指向自己过去",
        ],
    )
    # 3 个 scene 已落库，对应 3 个 beat；我们正在写第 2 个 scene
    scenes = [
        Scene(
            id=new_id("scene"), organization_id=org_id, project_id=project_id,
            chapter_id=chapter.id, scene_index=i + 1, title=f"场景{i + 1}",
            time_marker="", location="", characters=[], goal="", conflict="",
            emotion_start="", emotion_end="", reveal="", hook="", status="planned",
        )
        for i in range(3)
    ]
    db_session.add_all([spec, chapter, *scenes])
    await db_session.commit()

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scenes[1]
    )
    labels = [s.label for s in ctx.segments]
    assert "chapter_arc" in labels
    arc_seg = next(s for s in ctx.segments if s.label == "chapter_arc")
    assert arc_seg.trusted is True
    # 三条 beat 都出现
    assert "主角接到神秘电话" in arc_seg.content
    assert "追查电话来源" in arc_seg.content
    assert "线索指向自己过去" in arc_seg.content
    # 当前位置标号：第 2 场
    assert "→ 2" in arc_seg.content
    assert "你现在在写第 2/3 场" in arc_seg.content


@pytest.mark.asyncio
async def test_chapter_arc_empty_when_no_beats(client, db_session):
    from sqlalchemy import select

    token, project_id = await _register_with_project(client, "e3-empty@example.com")
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
        target_words=0, scene_beats=[],
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
    arc_seg = next(s for s in ctx.segments if s.label == "chapter_arc")
    assert arc_seg.content == ""
    # to_prompt 跳过空段
    assert "[chapter_arc]" not in ctx.to_prompt()


def test_budget_sums_to_one():
    from app.services.context_builder.service import _SEGMENT_BUDGET_PCT

    total = sum(_SEGMENT_BUDGET_PCT.values())
    assert abs(total - 1.0) < 1e-6, total
    assert "chapter_arc" in _SEGMENT_BUDGET_PCT
