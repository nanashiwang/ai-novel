"""信息释放 ledger 测试（Sprint 14-C5）。

覆盖：
- CRUD：list/create/update/status toggle/delete
- LedgerService.validate_reveal：secret fact 被 draft 命中且 scene 角色不在
  owners ∪ disclosed_to → high severity 违规
- ContextBuilder：information_visibility 段输出 partial/public 事实，
  secret 不进 prompt；总预算和保持 1.0
"""
from __future__ import annotations

import pytest
from sqlalchemy import select


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
            "title": "信息释放 ledger 项目",
            "premise": "城市档案员追查身份谜团。",
            "genre": "悬疑",
            "style": "克制",
            "target_reader": "成人读者",
        },
    )
    assert project.status_code in (200, 201), project.text
    return token, org_id, project.json()["id"]


@pytest.mark.asyncio
async def test_information_ledger_crud_roundtrip(client):
    """端到端 CRUD：创建 → 列表 → PATCH → 切 status → DELETE。"""
    token, _, project_id = await _register_with_project(
        client, "ledger-crud@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/projects/{project_id}/information-ledger"

    # 列表初始空
    res = await client.get(base, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json() == []

    # 创建
    payload = {
        "fact": "主角的真实身份是「夜行者首领」",
        "owners": ["林澈"],
        "disclosed_to": [],
        "planned_reveal_chapter": 8,
        "status": "secret",
        "importance": 5,
    }
    res = await client.post(base, headers=headers, json=payload)
    assert res.status_code == 201, res.text
    entry = res.json()
    entry_id = entry["id"]
    assert entry["status"] == "secret"
    assert entry["owners"] == ["林澈"]
    assert entry["planned_reveal_chapter"] == 8

    # 列表
    res = await client.get(base, headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1

    # PATCH
    res = await client.patch(
        f"{base}/{entry_id}",
        headers=headers,
        json={"disclosed_to": ["林澈", "苏怀玦"], "importance": 4},
    )
    assert res.status_code == 200, res.text
    assert res.json()["disclosed_to"] == ["林澈", "苏怀玦"]
    assert res.json()["importance"] == 4

    # 切换 status
    res = await client.patch(
        f"{base}/{entry_id}/status",
        headers=headers,
        json={"status": "partial"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "partial"

    # 删除
    res = await client.delete(f"{base}/{entry_id}", headers=headers)
    assert res.status_code == 204, res.text
    res = await client.get(base, headers=headers)
    assert res.json() == []


@pytest.mark.asyncio
async def test_information_ledger_update_404_for_other_project(client):
    """跨项目 PATCH 不应命中。"""
    token, _, project_id = await _register_with_project(
        client, "ledger-isolation@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/projects/{project_id}/information-ledger"
    res = await client.post(
        base,
        headers=headers,
        json={"fact": "「真凶身份」", "status": "secret"},
    )
    entry_id = res.json()["id"]
    # 用一个不存在的 project_id 访问该 entry
    other = f"/api/v1/projects/project_nonexistent/information-ledger/{entry_id}"
    res = await client.patch(other, headers=headers, json={"status": "public"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_validate_reveal_triggers_high_violation_when_outsider_speaks(
    client, db_session
):
    """构造一条 secret fact + 一个 draft 提到该 fact，但 scene character 不在
    owners 中 → 应触发 high severity violation。"""
    from app.models import Chapter, InformationLedger, Scene
    from app.models.common import new_id
    from app.services.ledger import ledger_service

    _token, org_id, project_id = await _register_with_project(
        client, "ledger-validate@example.com"
    )

    # 添加 chapter + scene + ledger fact
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=3,
        title="第三章",
        summary="对峙",
        goal="揭穿",
        conflict="冲突",
        ending_hook="钩子",
        status="planned",
    )
    db_session.add(chapter)
    await db_session.flush()
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=2,
        title="档案室对峙",
        time_marker="深夜",
        location="档案室",
        characters=["陈墨"],  # 陈墨不在 owners
        goal="对话",
        conflict="互相试探",
        emotion_start="紧张",
        emotion_end="决断",
        reveal="",
        hook="",
        status="drafted",
    )
    db_session.add(scene)
    ledger_row = InformationLedger(
        id=new_id("ledger"),
        organization_id=org_id,
        project_id=project_id,
        fact="主角的真实身份是「夜行者首领」",
        owners=["林澈"],
        disclosed_to=["苏怀玦"],
        status="secret",
        importance=5,
    )
    db_session.add(ledger_row)
    await db_session.commit()

    draft_content = (
        "陈墨低声说出了那个名字：「夜行者首领」。"
        "档案室里突然安静下来——他怎么会知道？"
    )
    violations = await ledger_service.validate_reveal(
        db_session,
        project_id=project_id,
        scene=scene,
        draft_content=draft_content,
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.fact_id == ledger_row.id
    assert v.severity == "high"  # importance=5 → high
    assert "夜行者首领" in v.description


@pytest.mark.asyncio
async def test_validate_reveal_silent_when_owner_present(client, db_session):
    """同样的 secret fact，但 scene 角色是 owner → 不视为违规。"""
    from app.models import Chapter, InformationLedger, Scene
    from app.models.common import new_id
    from app.services.ledger import ledger_service

    _token, org_id, project_id = await _register_with_project(
        client, "ledger-silent@example.com"
    )

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="第一章",
        summary="独白",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    db_session.add(chapter)
    await db_session.flush()
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="自言自语",
        time_marker="清晨",
        location="阁楼",
        characters=["林澈"],  # owner 出现在场景
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="drafted",
    )
    db_session.add(scene)
    db_session.add(
        InformationLedger(
            id=new_id("ledger"),
            organization_id=org_id,
            project_id=project_id,
            fact="主角的真实身份是「夜行者首领」",
            owners=["林澈"],
            disclosed_to=[],
            status="secret",
            importance=5,
        )
    )
    await db_session.commit()

    draft_content = "林澈对着镜子默念那个旧称号——「夜行者首领」。"
    violations = await ledger_service.validate_reveal(
        db_session,
        project_id=project_id,
        scene=scene,
        draft_content=draft_content,
    )
    assert violations == []


@pytest.mark.asyncio
async def test_validate_reveal_ignores_partial_and_public(client, db_session):
    """status != secret 的事实不应触发违规，无论是谁在 scene 中。"""
    from app.models import Chapter, InformationLedger, Scene
    from app.models.common import new_id
    from app.services.ledger import ledger_service

    _token, org_id, project_id = await _register_with_project(
        client, "ledger-public@example.com"
    )

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=10,
        title="后期",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    db_session.add(chapter)
    await db_session.flush()
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="公开揭示之后",
        time_marker="正午",
        location="广场",
        characters=["路人甲"],
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="drafted",
    )
    db_session.add(scene)
    db_session.add(
        InformationLedger(
            id=new_id("ledger"),
            organization_id=org_id,
            project_id=project_id,
            fact="主角的真实身份是「夜行者首领」",
            owners=["林澈"],
            disclosed_to=["全城百姓"],
            status="public",
            importance=5,
        )
    )
    await db_session.commit()

    draft_content = "路人甲指着告示牌说：「夜行者首领」原来就在我们中间。"
    violations = await ledger_service.validate_reveal(
        db_session,
        project_id=project_id,
        scene=scene,
        draft_content=draft_content,
    )
    assert violations == []


@pytest.mark.asyncio
async def test_context_builder_information_visibility_segment(client, db_session):
    """ContextBuilder 注入 information_visibility 段，partial/public 进 prompt，
    secret 不进。"""
    from app.models import Chapter, InformationLedger, NovelSpec, Project, Scene
    from app.models.common import new_id
    from app.services.context_builder import ContextBuilder

    _token, org_id, project_id = await _register_with_project(
        client, "ledger-ctx@example.com"
    )

    project = (
        await db_session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one()

    spec = (
        await db_session.execute(
            select(NovelSpec).where(NovelSpec.project_id == project_id)
        )
    ).scalar_one()
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=5,
        title="",
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
        title="",
        time_marker="",
        location="",
        characters=[],
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="planned",
    )
    secret_row = InformationLedger(
        id=new_id("ledger"),
        organization_id=org_id,
        project_id=project_id,
        fact="主角藏着的秘密剑 SECRET_KEYWORD",
        owners=["林澈"],
        disclosed_to=[],
        status="secret",
        importance=5,
    )
    partial_row = InformationLedger(
        id=new_id("ledger"),
        organization_id=org_id,
        project_id=project_id,
        fact="王城曾经发生过 PARTIAL_KEYWORD 暴动",
        owners=["史官"],
        disclosed_to=["林澈"],
        status="partial",
        importance=3,
    )
    public_row = InformationLedger(
        id=new_id("ledger"),
        organization_id=org_id,
        project_id=project_id,
        fact="新王登基的 PUBLIC_KEYWORD 庆典已公告全城",
        owners=["朝廷"],
        disclosed_to=["全城百姓"],
        status="public",
        importance=4,
    )
    db_session.add_all([chapter, scene, secret_row, partial_row, public_row])
    await db_session.commit()

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    labels = [s.label for s in ctx.segments]
    assert "information_visibility" in labels

    info_seg = next(s for s in ctx.segments if s.label == "information_visibility")
    assert info_seg.trusted is True
    assert "PARTIAL_KEYWORD" in info_seg.content
    assert "PUBLIC_KEYWORD" in info_seg.content
    # secret 永远不进 prompt（保留信息差对剧情张力的作用）
    assert "SECRET_KEYWORD" not in info_seg.content
    assert "SECRET_KEYWORD" not in ctx.to_prompt()


@pytest.mark.asyncio
async def test_context_builder_budget_sums_to_one():
    """预算分配字典之和恒为 1.0，避免新增段时漏调比例。"""
    from app.services.context_builder.service import _SEGMENT_BUDGET_PCT

    assert "information_visibility" in _SEGMENT_BUDGET_PCT
    total = sum(_SEGMENT_BUDGET_PCT.values())
    assert abs(total - 1.0) < 1e-9, _SEGMENT_BUDGET_PCT


@pytest.mark.asyncio
async def test_context_builder_information_visibility_empty_when_no_visible(
    client, db_session
):
    """没有 partial/public 事实时段为空，to_prompt() 跳过 information_visibility 标题。"""
    from app.models import Chapter, InformationLedger, NovelSpec, Project, Scene
    from app.models.common import new_id
    from app.services.context_builder import ContextBuilder

    _token, org_id, project_id = await _register_with_project(
        client, "ledger-ctx-empty@example.com"
    )

    project = (
        await db_session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one()
    spec = (
        await db_session.execute(
            select(NovelSpec).where(NovelSpec.project_id == project_id)
        )
    ).scalar_one()
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="",
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
        title="",
        time_marker="",
        location="",
        characters=[],
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="planned",
    )
    # 仅一条 secret，不应出现在 prompt
    db_session.add(chapter)
    db_session.add(scene)
    db_session.add(
        InformationLedger(
            id=new_id("ledger"),
            organization_id=org_id,
            project_id=project_id,
            fact="未公开内容",
            owners=["主角"],
            disclosed_to=[],
            status="secret",
            importance=3,
        )
    )
    await db_session.commit()

    builder = ContextBuilder(total_budget=8000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    info_seg = next(s for s in ctx.segments if s.label == "information_visibility")
    assert info_seg.content == ""
    assert "information_visibility" not in ctx.to_prompt()
