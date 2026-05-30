from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    Chapter,
    ChapterStateRequirement,
    Project,
    Scene,
    StoryStateItem,
)
from app.models.common import new_id
from app.services.story_state.service import StoryStateInput, story_state_service


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": email.split("@")[0],
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


def _project_chapters_and_state() -> tuple[Project, Chapter, Chapter, StoryStateItem]:
    org_id = new_id("org")
    project_id = new_id("project")
    project = Project(
        id=project_id,
        organization_id=org_id,
        created_by="user_x",
        title="承接传播测试",
        target_word_count=100_000,
        target_chapter_count=20,
        status="drafting",
    )
    current = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=4,
        title="戒律堂冷审",
        summary="旧铜钱被戒律堂禁制。",
        goal="留下七日喘息期",
        conflict="戒律堂不信任林照夜",
        ending_hook="杂役院期限将至",
        status="planned",
    )
    next_chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=5,
        title="外门第一辱",
        summary="林照夜入杂役院。",
        goal="承接戒律堂外周承岳的试探",
        conflict="外门弟子欺压杂役",
        ending_hook="旧铜钱禁制再响",
        status="planned",
    )
    state = StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="artifact",
        entity_id=None,
        state_type="artifact",
        name="旧铜钱",
        status="active",
        summary="旧铜钱带有戒律堂霜纹禁制，七日内不能随意丢弃。",
        value_json={"restriction": "七日禁制"},
        source_chapter_id=current.id,
        source_scene_id=None,
        source_excerpt="旧铜钱表面结出霜纹。",
        updated_in_chapter_id=current.id,
        priority=100,
        is_hard_constraint=True,
    )
    return project, current, next_chapter, state


@pytest.mark.asyncio
async def test_rebuild_requirements_propagates_next_chapter_hints(db_session):
    project, current, next_chapter, state = _project_chapters_and_state()
    db_session.add_all([project, current, next_chapter, state])
    await db_session.commit()

    state_input = StoryStateInput(
        entity_type=state.entity_type,
        entity_id=state.entity_id,
        state_type=state.state_type,
        name=state.name,
        summary=state.summary,
        status=state.status,
        priority=100,
        is_hard_constraint=True,
        requirement_type="must_remember",
        requirement_hint="下一章应承接林照夜成为外门杂役，且旧铜钱仍带霜纹禁制。",
    )

    result = await story_state_service.rebuild_chapter_requirements(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        chapter=current,
        scene=None,
        state_inputs=[state_input],
    )
    await db_session.commit()

    assert result["created"] == 1
    assert result["next_chapter_created"] == 1
    rows = (
        await db_session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.project_id == project.id
            )
        )
    ).scalars().all()
    by_chapter = {row.chapter_id: row for row in rows}
    assert current.id in by_chapter
    assert next_chapter.id in by_chapter
    assert by_chapter[next_chapter.id].summary == state_input.requirement_hint
    assert by_chapter[current.id].origin_type == "current_chapter_extract"
    assert by_chapter[current.id].source_chapter_id == current.id
    assert by_chapter[current.id].target_chapter_id == current.id
    assert by_chapter[next_chapter.id].origin_type == "previous_chapter_carryover"
    assert by_chapter[next_chapter.id].source_chapter_id == current.id
    assert by_chapter[next_chapter.id].target_chapter_id == next_chapter.id

    # 重跑同一批提取结果时，下一章不应重复插入相同承接要求。
    result = await story_state_service.rebuild_chapter_requirements(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        chapter=current,
        scene=None,
        state_inputs=[state_input],
    )
    await db_session.commit()

    assert result["next_chapter_created"] == 0
    count = (
        await db_session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.project_id == project.id,
                ChapterStateRequirement.chapter_id == next_chapter.id,
            )
        )
    ).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_rebuild_preserves_forward_requirements_from_previous_chapter(db_session):
    project, current, next_chapter, state = _project_chapters_and_state()
    db_session.add_all([project, current, next_chapter, state])
    await db_session.commit()

    preserved = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=next_chapter.id,
        state_item_id=state.id,
        requirement_type="must_not_conflict",
        summary="后续七日内旧铜钱应带有霜纹禁制，林照夜不能随意弃钱。",
        priority=100,
        origin_type="previous_chapter_carryover",
        source_chapter_id=current.id,
        target_chapter_id=next_chapter.id,
    )
    rebuildable = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=next_chapter.id,
        state_item_id=state.id,
        requirement_type="must_remember",
        summary="本章必须补写一次杂役院冲突。",
        priority=80,
    )
    db_session.add_all([preserved, rebuildable])
    await db_session.commit()

    result = await story_state_service.rebuild_chapter_requirements(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        chapter=next_chapter,
        scene=None,
        state_inputs=[],
    )
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.project_id == project.id,
                ChapterStateRequirement.chapter_id == next_chapter.id,
            )
        )
    ).scalars().all()
    assert result["deleted"] == 1
    assert [row.summary for row in rows] == [preserved.summary]
    assert rows[0].origin_type == "previous_chapter_carryover"


@pytest.mark.asyncio
async def test_state_requirements_api_returns_source_metadata(client, db_session):
    token, org_id = await _register(client, "state-req-source@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "承接来源 API 测试", "target_word_count": 100_000},
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    source_chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=4,
        title="戒律堂冷审",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    target_chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=5,
        title="外门第一辱",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    state = StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="artifact",
        entity_id=None,
        state_type="artifact",
        name="旧铜钱",
        status="active",
        summary="旧铜钱带有戒律堂霜纹禁制。",
        value_json={},
        source_chapter_id=source_chapter.id,
        source_scene_id=None,
        source_excerpt="",
        updated_in_chapter_id=source_chapter.id,
        priority=100,
        is_hard_constraint=True,
    )
    requirement = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=target_chapter.id,
        state_item_id=state.id,
        requirement_type="must_remember",
        summary="下一章应承接林照夜成为外门杂役。",
        priority=100,
        origin_type="previous_chapter_carryover",
        source_chapter_id=source_chapter.id,
        target_chapter_id=target_chapter.id,
    )
    db_session.add_all([source_chapter, target_chapter, state, requirement])
    await db_session.commit()

    res = await client.get(
        f"/api/v1/projects/{project_id}/chapters/{target_chapter.id}/state-requirements",
        headers=headers,
    )

    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["origin_type"] == "previous_chapter_carryover"
    assert item["source_chapter_id"] == source_chapter.id
    assert item["source_chapter_index"] == 4
    assert item["source_chapter_title"] == "戒律堂冷审"
    assert item["target_chapter_id"] == target_chapter.id
    assert item["state_item"]["id"] == state.id


@pytest.mark.asyncio
async def test_scene_anti_forgetting_preview_returns_injected_rows(client, db_session):
    token, org_id = await _register(client, "state-req-preview@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "写作前注入预览测试", "target_word_count": 100_000},
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=8,
        title="夜闯丹房",
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
        title="灰线照见毒丹",
        time_marker="深夜",
        location="丹房",
        characters=["林照夜"],
        scene_purpose="承接左眼代价并发现毒丹。",
        entry_state="潜入丹房",
        exit_state="发现毒丹",
        goal="找到外门陷害证据",
        conflict="丹房禁制压制灵识",
        must_include=[],
        must_avoid=[],
        emotion_start="警惕",
        emotion_end="震惊",
        reveal="毒丹证据",
        hook="左眼再次刺痛",
        status="planned",
    )
    state = StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="character",
        entity_id="lin_zhaoye",
        state_type="skill",
        name="林照夜",
        status="active",
        summary="林照夜能短暂看见因果灰线，代价是左眼刺痛。",
        value_json={},
        source_chapter_id=chapter.id,
        source_scene_id=scene.id,
        source_excerpt="左眼刺痛，灰线浮现。",
        updated_in_chapter_id=chapter.id,
        priority=95,
        is_hard_constraint=True,
    )
    requirement = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        target_chapter_id=chapter.id,
        state_item_id=state.id,
        requirement_type="must_remember",
        summary="本章必须承接灰线能力的左眼代价。",
        priority=98,
        origin_type="manual",
    )
    db_session.add_all([chapter, scene, state, requirement])
    await db_session.commit()

    res = await client.get(
        f"/api/v1/projects/{project_id}/scenes/{scene.id}/anti-forgetting-preview",
        headers=headers,
    )

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["scene_id"] == scene.id
    assert data["chapter_id"] == chapter.id
    assert data["meta"]["anti_forgetting_state_count"] >= 1
    assert data["meta"]["anti_forgetting_requirement_count"] == 1
    assert data["requirements"][0]["id"] == requirement.id
    assert data["requirements"][0]["origin_type"] == "manual"
    assert data["requirements"][0]["state_item"]["id"] == state.id
    assert data["story_states"][0]["id"] == state.id
    assert f"requirement_id={requirement.id}" in data["prompt_block"]
    assert f"story_state_item_id={state.id}" in data["prompt_block"]


@pytest.mark.asyncio
async def test_state_requirements_api_supports_manual_correction(client, db_session):
    token, org_id = await _register(client, "state-req-manual@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "承接要求人工修正测试", "target_word_count": 100_000},
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=6,
        title="杂役院夜斗",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    state = StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="character",
        entity_id="lin_zhaoye",
        state_type="skill",
        name="因果灰线视野",
        status="active",
        summary="林照夜只能短暂看见因果灰线，过度使用会刺痛左眼。",
        value_json={},
        source_chapter_id=chapter.id,
        source_scene_id=None,
        source_excerpt="左眼刺痛，灰线浮现。",
        updated_in_chapter_id=chapter.id,
        priority=92,
        is_hard_constraint=True,
    )
    db_session.add_all([chapter, state])
    await db_session.commit()

    create_res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter.id}/state-requirements",
        headers=headers,
        json={
            "state_item_id": state.id,
            "requirement_type": "must_remember",
            "summary": "本章必须承接因果灰线视野的左眼代价。",
            "priority": 88,
        },
    )
    assert create_res.status_code == 201, create_res.text
    created = create_res.json()
    assert created["origin_type"] == "manual"
    assert created["state_item"]["id"] == state.id
    assert created["summary"] == "本章必须承接因果灰线视野的左眼代价。"

    patch_res = await client.patch(
        (
            f"/api/v1/projects/{project_id}/chapters/{chapter.id}/state-requirements/"
            f"{created['id']}"
        ),
        headers=headers,
        json={
            "requirement_type": "must_not_conflict",
            "summary": "不能把因果灰线写成无限制常驻能力。",
            "priority": 96,
        },
    )
    assert patch_res.status_code == 200, patch_res.text
    patched = patch_res.json()
    assert patched["origin_type"] == "manual"
    assert patched["requirement_type"] == "must_not_conflict"
    assert patched["summary"] == "不能把因果灰线写成无限制常驻能力。"
    assert patched["priority"] == 96

    delete_res = await client.delete(
        (
            f"/api/v1/projects/{project_id}/chapters/{chapter.id}/state-requirements/"
            f"{created['id']}"
        ),
        headers=headers,
    )
    assert delete_res.status_code == 204, delete_res.text
    list_res = await client.get(
        f"/api/v1/projects/{project_id}/chapters/{chapter.id}/state-requirements",
        headers=headers,
    )
    assert list_res.status_code == 200, list_res.text
    assert list_res.json()["items"] == []


@pytest.mark.asyncio
async def test_rebuild_preserves_manual_requirements(db_session):
    project, current, _, state = _project_chapters_and_state()
    db_session.add_all([project, current, state])
    await db_session.commit()

    manual = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=current.id,
        target_chapter_id=current.id,
        state_item_id=state.id,
        requirement_type="must_remember",
        summary="人工要求：本章必须写出旧铜钱禁制仍在。",
        priority=90,
        origin_type="manual",
    )
    rebuildable = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=current.id,
        target_chapter_id=current.id,
        state_item_id=state.id,
        requirement_type="should_reference",
        summary="自动旧要求，重建时可以删除。",
        priority=50,
        origin_type="current_chapter_extract",
    )
    db_session.add_all([manual, rebuildable])
    await db_session.commit()

    result = await story_state_service.rebuild_chapter_requirements(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        chapter=current,
        scene=None,
        state_inputs=[],
    )
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.project_id == project.id,
                ChapterStateRequirement.chapter_id == current.id,
            )
        )
    ).scalars().all()
    assert result["deleted"] == 1
    assert len(rows) == 1
    assert rows[0].id == manual.id
    assert rows[0].origin_type == "manual"
