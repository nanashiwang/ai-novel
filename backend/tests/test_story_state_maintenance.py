from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.models import (
    Chapter,
    ChapterStateRequirement,
    ContinuityIssue,
    DraftVersion,
    Project,
    Scene,
    StoryStateHistory,
    StoryStateItem,
    StoryStateMaintenanceAction,
)
from app.models.common import new_id
from app.services.story_state.maintainer import story_state_maintainer_service


def _base_scene() -> tuple[str, Project, Chapter, Scene, DraftVersion]:
    org_id = new_id("org")
    user_id = new_id("user")
    project = Project(
        id=new_id("project"),
        organization_id=org_id,
        created_by=user_id,
        title="AI 关键设定维护测试",
        target_word_count=100_000,
        target_chapter_count=80,
        status="drafting",
    )
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project.id,
        volume_id=None,
        chapter_index=12,
        title="青冥洗瞳",
        summary="林照夜得到缓解眼痛的异宝。",
        goal="解决因果灰线代价",
        conflict="丹房禁制压制灵识",
        ending_hook="灰线再度浮现",
        status="planned",
    )
    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_index=1,
        title="青冥入眼",
        time_marker="深夜",
        location="丹房",
        characters=["林照夜"],
        scene_purpose="写出青冥洗瞳露缓解因果灰线的眼痛。",
        entry_state="左眼刺痛",
        exit_state="代价变为短暂酸胀",
        goal="缓解眼痛",
        conflict="禁制反噬",
        must_include=[],
        must_avoid=[],
        emotion_start="紧张",
        emotion_end="镇定",
        reveal="异宝可缓解旧代价",
        hook="灰线变得更清晰",
        status="planned",
    )
    draft = DraftVersion(
        id=new_id("draft"),
        organization_id=org_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        version_type="draft",
        content="青冥洗瞳露化作凉意入眼，旧日针扎般的剧痛只剩短暂酸胀。",
        content_format="markdown",
        word_count=34,
        status="draft",
        parent_version_id=None,
        created_by=user_id,
    )
    return user_id, project, chapter, scene, draft


def _state(
    *,
    org_id: str,
    project_id: str,
    chapter_id: str,
    scene_id: str | None,
    name: str = "因果灰线视野",
    summary: str = "林照夜能短暂看见因果灰线，代价是左眼剧痛。",
    priority: int = 80,
) -> StoryStateItem:
    return StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="character",
        entity_id="lin_zhaoye",
        state_type="skill",
        name=name,
        status="active",
        summary=summary,
        value_json={"cost": "left_eye_pain"},
        source_chapter_id=chapter_id,
        source_scene_id=scene_id,
        source_excerpt="左眼刺痛，灰线浮现。",
        updated_in_chapter_id=chapter_id,
        priority=priority,
        is_hard_constraint=True,
    )


async def _run_with_response(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
    *,
    response: dict[str, Any],
    user_id: str,
    project: Project,
    chapter: Chapter,
    scene: Scene,
    draft: DraftVersion,
) -> dict[str, Any]:
    async def fake_generate_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return response

    monkeypatch.setattr(
        "app.services.story_state.maintainer.model_gateway.generate_json",
        fake_generate_json,
    )
    return await story_state_maintainer_service.maintain_after_draft(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        job_id="job_test",
        chapter=chapter,
        scene=scene,
        draft=draft,
        created_by=user_id,
    )


@pytest.mark.asyncio
async def test_story_state_maintainer_applies_low_risk_update(monkeypatch, db_session):
    user_id, project, chapter, scene, draft = _base_scene()
    state = _state(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
    )
    db_session.add_all([project, chapter, scene, draft, state])
    await db_session.commit()

    result = await _run_with_response(
        monkeypatch,
        db_session,
        response={
            "actions": [
                {
                    "type": "update_state",
                    "target_state_id": state.id,
                    "confidence": 0.91,
                    "risk_level": "low",
                    "reason": "正文明确写出旧剧痛被缓解为酸胀",
                    "patch": {
                        "summary": "因果灰线视野可看见因果线，使用后左眼只会短暂酸胀。",
                        "value_json": {"cost": "short_eye_soreness"},
                    },
                }
            ]
        },
        user_id=user_id,
        project=project,
        chapter=chapter,
        scene=scene,
        draft=draft,
    )
    await db_session.commit()

    assert result["applied_count"] == 1
    await db_session.refresh(state)
    assert state.summary == "因果灰线视野可看见因果线，使用后左眼只会短暂酸胀。"
    assert state.value_json["cost"] == "short_eye_soreness"

    actions = (
        await db_session.execute(select(StoryStateMaintenanceAction))
    ).scalars().all()
    assert len(actions) == 1
    assert actions[0].status == "applied"
    assert actions[0].target_state_id == state.id
    assert actions[0].before_json["target"]["summary"] == (
        "林照夜能短暂看见因果灰线，代价是左眼剧痛。"
    )

    history = (await db_session.execute(select(StoryStateHistory))).scalars().all()
    assert len(history) == 1
    assert history[0].state_item_id == state.id
    assert history[0].change_type == "update"


@pytest.mark.asyncio
async def test_story_state_maintainer_merges_states_and_rewires_links(monkeypatch, db_session):
    user_id, project, chapter, scene, draft = _base_scene()
    target = _state(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        name="因果灰线视野",
        priority=80,
    )
    duplicate = _state(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        name="因果灰线",
        summary="因果灰线能力可追索丹药因果，也会带来眼部代价。",
        priority=95,
    )
    requirement = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        target_chapter_id=chapter.id,
        state_item_id=duplicate.id,
        requirement_type="must_remember",
        summary="本章必须承接因果灰线的眼部代价。",
        priority=90,
        origin_type="manual",
    )
    issue = ContinuityIssue(
        id=new_id("issue"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        story_state_item_id=duplicate.id,
        issue_type="state_conflict",
        severity="medium",
        description="重复关键设定导致审稿引用了旧 ID。",
        suggested_fix="合并重复关键设定。",
        status="open",
    )
    db_session.add_all([project, chapter, scene, draft, target, duplicate, requirement, issue])
    await db_session.commit()

    result = await _run_with_response(
        monkeypatch,
        db_session,
        response={
            "actions": [
                {
                    "type": "merge_states",
                    "target_state_id": target.id,
                    "source_state_ids": [duplicate.id],
                    "confidence": 0.94,
                    "risk_level": "low",
                    "reason": "两条设定都是林照夜的因果灰线能力",
                    "patch": {
                        "summary": "因果灰线视野可追索因果，早期使用会造成眼部代价。"
                    },
                }
            ]
        },
        user_id=user_id,
        project=project,
        chapter=chapter,
        scene=scene,
        draft=draft,
    )
    await db_session.commit()

    assert result["applied_count"] == 1
    await db_session.refresh(target)
    await db_session.refresh(duplicate)
    await db_session.refresh(requirement)
    await db_session.refresh(issue)
    assert target.summary == "因果灰线视野可追索因果，早期使用会造成眼部代价。"
    assert target.priority == 95
    assert duplicate.status == "inactive"
    assert duplicate.superseded_by_state_id == target.id
    assert requirement.state_item_id == target.id
    assert issue.story_state_item_id == target.id

    action = (await db_session.execute(select(StoryStateMaintenanceAction))).scalar_one()
    assert action.status == "applied"
    assert action.source_state_ids == [duplicate.id]
    assert action.after_json["updated_requirement_count"] == 1
    assert action.after_json["updated_issue_count"] == 1


@pytest.mark.asyncio
async def test_story_state_maintainer_resolves_requirement(monkeypatch, db_session):
    user_id, project, chapter, scene, draft = _base_scene()
    state = _state(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
    )
    requirement = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        target_chapter_id=chapter.id,
        state_item_id=state.id,
        requirement_type="must_remember",
        summary="本章必须承接因果灰线的眼部代价。",
        priority=90,
        origin_type="manual",
        status="active",
    )
    db_session.add_all([project, chapter, scene, draft, state, requirement])
    await db_session.commit()

    result = await _run_with_response(
        monkeypatch,
        db_session,
        response={
            "actions": [
                {
                    "type": "resolve_requirement",
                    "target_requirement_id": requirement.id,
                    "confidence": 0.9,
                    "risk_level": "low",
                    "reason": "正文已经承接眼部代价",
                    "patch": {"status_reason": "当前 scene 已兑现"},
                }
            ]
        },
        user_id=user_id,
        project=project,
        chapter=chapter,
        scene=scene,
        draft=draft,
    )
    await db_session.commit()

    assert result["applied_count"] == 1
    await db_session.refresh(requirement)
    assert requirement.status == "resolved"
    assert requirement.status_reason == "当前 scene 已兑现"

    action = (await db_session.execute(select(StoryStateMaintenanceAction))).scalar_one()
    assert action.status == "applied"
    assert action.target_requirement_id == requirement.id
    assert action.target_state_id == state.id


@pytest.mark.asyncio
async def test_story_state_maintainer_logs_high_risk_without_applying(monkeypatch, db_session):
    user_id, project, chapter, scene, draft = _base_scene()
    state = _state(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
    )
    db_session.add_all([project, chapter, scene, draft, state])
    await db_session.commit()

    result = await _run_with_response(
        monkeypatch,
        db_session,
        response={
            "actions": [
                {
                    "type": "update_state",
                    "target_state_id": state.id,
                    "confidence": 0.99,
                    "risk_level": "high",
                    "reason": "试图改写主角核心能力规则",
                    "patch": {"summary": "因果灰线成为无代价常驻能力。"},
                }
            ]
        },
        user_id=user_id,
        project=project,
        chapter=chapter,
        scene=scene,
        draft=draft,
    )
    await db_session.commit()

    assert result["needs_review_count"] == 1
    await db_session.refresh(state)
    assert state.summary == "林照夜能短暂看见因果灰线，代价是左眼剧痛。"

    action = (await db_session.execute(select(StoryStateMaintenanceAction))).scalar_one()
    assert action.status == "needs_review"
    assert action.before_json == action.after_json
