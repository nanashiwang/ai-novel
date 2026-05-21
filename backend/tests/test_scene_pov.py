"""Per-scene POV 锚定 + 视角隔离测试（Sprint 14-C6）。

覆盖：
- scene.pov_character_name 非空时：仅 POV 角色展示 secret/motivation/arc/
  current_state；非 POV 角色这些字段被过滤掉，但 description + role +
  (POV 已知的关系) 保留
- pov_character_name 为空时：退回原"全部展示"行为（向后兼容）
- task 段加入"POV 视角主角"行；非 POV 时该行不出现
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
        json={"title": "C6 POV 测试", "genre": "奇幻"},
    )
    assert project_res.status_code in (200, 201), project_res.text
    return token, project_res.json()["id"]


async def _seed_scene_with_two_characters(client, db_session, email: str, pov_name: str | None):
    """注入两个角色 + 一个 scene；返回 (project, spec, chapter, scene)。"""
    from sqlalchemy import select

    from app.models.chapter import Chapter
    from app.models.character import Character
    from app.models.common import new_id
    from app.models.project import NovelSpec, Project
    from app.models.scene import Scene

    token, project_id = await _register_with_project(client, email)
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
        premise="测试 POV",
        theme="背叛与救赎",
        genre="奇幻",
        tone="紧张",
        target_reader="—",
        narrative_pov="第三人称有限",
        style_guide="—",
        constraints=[],
        continuity_rules=[],
    )
    db_session.add(spec)

    hero = Character(
        id=new_id("char"),
        organization_id=org_id,
        project_id=project_id,
        name="主角A",
        role="protagonist",
        description="少年剑士",
        personality="冲动而正义",
        motivation="为亡父复仇",
        secret="其实是失忆王族",
        arc="从冲动到沉稳的领导者",
        relationships={"反派B": "宿敌；对方曾在童年时救过自己"},
        current_state={"hp": "高", "mood": "焦虑"},
    )
    villain = Character(
        id=new_id("char"),
        organization_id=org_id,
        project_id=project_id,
        name="反派B",
        role="antagonist",
        description="黑袍法师",
        personality="阴鸷多疑",
        motivation="复活上古暴君",
        secret="背后是黑魔王",
        arc="从忠仆走向自立的反叛者",
        relationships={"主角A": "宿敌；不知主角真实身份"},
        current_state={"hp": "中", "mood": "蛰伏"},
    )

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="重逢",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="drafted",
    )
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="对峙",
        time_marker="",
        location="",
        characters=["主角A", "反派B"],
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="planned",
        pov_character_name=pov_name,
    )
    db_session.add_all([hero, villain, chapter, scene])
    await db_session.commit()
    return project, spec, chapter, scene


@pytest.mark.asyncio
async def test_pov_filter_hides_non_pov_secrets(client, db_session):
    """主角A 视角下：反派B 的 secret/motivation/arc/current_state 不应进 prompt。"""
    from app.services.context_builder import ContextBuilder

    project, spec, chapter, scene = await _seed_scene_with_two_characters(
        client, db_session, "c6-pov-on@example.com", pov_name="主角A"
    )

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    char_seg = next(s for s in ctx.segments if s.label == "characters")
    content = char_seg.content
    prompt = ctx.to_prompt()

    # POV 自己：完整暴露
    assert "失忆王族" in content  # 主角A.secret
    assert "为亡父复仇" in content  # 主角A.motivation
    assert "从冲动到沉稳的领导者" in content  # 主角A.arc
    assert "[POV]" in content  # POV 标记

    # 非 POV：description + role 保留
    assert "黑袍法师" in content  # 反派B.description
    # 非 POV：secret/motivation/arc/current_state 被隐藏
    assert "背后是黑魔王" not in content  # 反派B.secret
    assert "复活上古暴君" not in content  # 反派B.motivation
    assert "从忠仆走向自立的反叛者" not in content  # 反派B.arc
    # current_state 中"蛰伏"是反派 B 独有词
    assert "蛰伏" not in content

    # POV 已知的双边关系应保留
    assert "与 主角A 的已知关系" in content
    assert "不知主角真实身份" in content

    # task 段应标注 POV
    task_seg = next(s for s in ctx.segments if s.label == "task")
    assert "POV 视角主角：主角A" in task_seg.content

    # 双重校验：组装好的 prompt 中也不能出现反派的 secret
    assert "背后是黑魔王" not in prompt
    assert "失忆王族" in prompt


@pytest.mark.asyncio
async def test_pov_none_falls_back_to_full_visibility(client, db_session):
    """无 POV 锚定时，沿用原行为：所有角色 secret/motivation 都展示。"""
    from app.services.context_builder import ContextBuilder

    project, spec, chapter, scene = await _seed_scene_with_two_characters(
        client, db_session, "c6-pov-off@example.com", pov_name=None
    )

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    char_seg = next(s for s in ctx.segments if s.label == "characters")
    content = char_seg.content

    # 两边的 secret 都应出现（向后兼容）
    assert "失忆王族" in content
    assert "背后是黑魔王" in content
    # 没有 POV 标记
    assert "[POV]" not in content

    # task 段不应出现 POV 行
    task_seg = next(s for s in ctx.segments if s.label == "task")
    assert "POV 视角主角" not in task_seg.content


@pytest.mark.asyncio
async def test_scene_patch_accepts_pov_field(client, db_session):
    """PATCH /scenes/{id} 应能写入 pov_character_name，且 GET 能读回。"""
    from sqlalchemy import select

    from app.models.chapter import Chapter
    from app.models.common import new_id
    from app.models.scene import Scene

    token, project_id = await _register_with_project(client, "c6-pov-patch@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org_id = me["organization_id"]

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="x",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="s",
        time_marker="",
        location="",
        characters=["主角A"],
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="planned",
    )
    db_session.add_all([chapter, scene])
    await db_session.commit()

    # PATCH
    res = await client.patch(
        f"/api/v1/projects/{project_id}/scenes/{scene.id}",
        headers=headers,
        json={
            "chapter_id": chapter.id,
            "scene_index": 1,
            "title": "s",
            "characters": ["主角A"],
            "pov_character_name": "主角A",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pov_character_name"] == "主角A"

    # 重新查 DB 验证持久化
    await db_session.commit()
    fresh = (
        await db_session.execute(select(Scene).where(Scene.id == scene.id))
    ).scalar_one()
    assert fresh.pov_character_name == "主角A"
