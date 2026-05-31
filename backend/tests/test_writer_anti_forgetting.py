from __future__ import annotations

from typing import Any

import pytest

from app.core.config import get_settings
from app.models import (
    Chapter,
    ChapterStateRequirement,
    ContinuityIssue,
    NovelSpec,
    Project,
    Scene,
    StoryStateItem,
)
from app.models.common import new_id
from app.services.rewriter import service as rewriter_module
from app.services.writer import service as writer_module


def _make_project_spec_chapter_scene() -> tuple[Project, NovelSpec, Chapter, Scene]:
    org_id = new_id("org")
    project_id = new_id("project")
    chapter_id = new_id("chapter")
    scene_id = new_id("scene")
    project = Project(
        id=project_id,
        organization_id=org_id,
        created_by="user_x",
        title="因果长生",
        genre="玄幻",
        target_word_count=1_000_000,
        target_chapter_count=500,
        language="zh-CN",
        style="爽文",
        status="drafting",
        cover_url="",
        tags=[],
        target_reader="男频读者",
    )
    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="主角以因果入仙道。",
        theme="因果有代价。",
        genre="玄幻修仙",
        tone="热血",
        target_reader="男频读者",
        narrative_pov="第三人称",
        style_guide="正文禁止 Markdown 加粗。",
        constraints=["因果印不能无代价使用"],
        continuity_rules=["因果印破损前不可完整逆转生死"],
    )
    chapter = Chapter(
        id=chapter_id,
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=12,
        title="因果印裂",
        summary="主角发现因果印出现裂痕。",
        goal="承接法宝破损状态",
        conflict="强敌逼迫主角强行催动因果印",
        ending_hook="裂痕里传出古老声音",
        status="planned",
        target_words=2600,
        scene_beats=["检查因果印", "强敌来袭", "裂痕反噬"],
    )
    scene = Scene(
        id=scene_id,
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter_id,
        scene_index=1,
        title="裂印反噬",
        time_marker="夜",
        location="废弃丹房",
        characters=["林渊"],
        scene_purpose="写出因果印破损后的使用限制",
        entry_state="因果印已有裂痕",
        exit_state="主角确认不能强行完整催动",
        goal="避开追杀",
        conflict="追兵封门",
        must_include=["因果印裂痕"],
        must_avoid=["把因果印写成完好无损"],
        emotion_start="警觉",
        emotion_end="压抑",
        reveal="裂痕会吞噬寿元",
        hook="裂痕中传来呼唤",
        status="drafted",
        target_words=1300,
        beat_start=1,
        beat_end=2,
        beat_group_summary="检查因果印；强敌来袭",
        budget_reason="2600 字章节自动拆为 2 场",
    )
    return project, spec, chapter, scene


def _make_state_and_requirement(
    *,
    org_id: str,
    project_id: str,
    chapter_id: str,
    scene_id: str,
    state_id: str,
) -> tuple[StoryStateItem, ChapterStateRequirement]:
    state = StoryStateItem(
        id=state_id,
        organization_id=org_id,
        project_id=project_id,
        entity_type="artifact",
        entity_id=None,
        state_type="artifact",
        name="因果印",
        status="damaged",
        summary="因果印已有裂痕，不能完整逆转生死。",
        value_json={"limitation": "强行催动会吞噬寿元"},
        source_chapter_id=chapter_id,
        source_scene_id=scene_id,
        source_excerpt="因果印表面浮现一道裂纹。",
        updated_in_chapter_id=chapter_id,
        priority=90,
        is_hard_constraint=True,
    )
    requirement = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter_id,
        state_item_id=state_id,
        requirement_type="must_remember",
        summary="本章必须承接因果印已损坏，不能写成完好无损。",
        priority=95,
    )
    return state, requirement


@pytest.mark.asyncio
async def test_writer_injects_anti_forgetting_block_before_generation(
    db_session,
    monkeypatch,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "writer_pipeline_mode", "single")

    project, spec, chapter, scene = _make_project_spec_chapter_scene()
    state_id = new_id("state")
    state, requirement = _make_state_and_requirement(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        state_id=state_id,
    )
    db_session.add_all([project, spec, chapter, scene, state, requirement])
    await db_session.commit()

    captured: dict[str, Any] = {}

    async def fake_generate_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured["user_prompt"] = kwargs["user_prompt"]
        captured["metadata"] = kwargs["metadata"]
        return {
            "scene_id": scene.id,
            "title": scene.title,
            "content": "因果印裂痕幽幽发烫，林渊没有强行完整催动。",
            "word_count": 24,
            "continuity_notes": [],
            "unresolved_threads": [],
        }

    monkeypatch.setattr(writer_module.model_gateway, "generate_json", fake_generate_json)

    draft = await writer_module.writer_service.write_scene_draft(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        job_id=new_id("job"),
        project=project,
        spec=spec,
        chapter=chapter,
        scene=scene,
        target_words=1300,
    )

    prompt = captured["user_prompt"]
    assert draft.content
    assert "## 写作防遗忘承接清单" in prompt
    assert "本章承接要求" in prompt
    assert state_id in prompt
    assert "status=damaged" in prompt
    assert "因果印已有裂痕" in prompt
    assert "不得被写成仍可正常使用" in prompt
    assert "正文中禁止输出 story_state_item_id" in prompt
    assert captured["metadata"]["anti_forgetting_state_count"] >= 1
    assert captured["metadata"]["anti_forgetting_requirement_count"] == 1


@pytest.mark.asyncio
async def test_rewriter_injects_linked_state_for_issue_repair(
    db_session,
    monkeypatch,
):
    project, spec, chapter, scene = _make_project_spec_chapter_scene()
    state_id = new_id("state")
    state, requirement = _make_state_and_requirement(
        org_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        state_id=state_id,
    )
    issue = ContinuityIssue(
        id=new_id("issue"),
        organization_id=project.organization_id,
        project_id=project.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        story_state_item_id=state_id,
        issue_type="state_conflict",
        severity="high",
        description="正文把因果印写成完好无损，与关键状态冲突。",
        suggested_fix="把催动因果印前的描写改为裂痕反噬，并补一句代价。",
        status="open",
    )
    db_session.add_all([project, spec, chapter, scene, state, requirement, issue])
    await db_session.commit()

    captured: dict[str, Any] = {}

    async def fake_generate_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured["user_prompt"] = kwargs["user_prompt"]
        captured["metadata"] = kwargs["metadata"]
        return {
            "scene_id": scene.id,
            "title": scene.title,
            "content": "因果印裂纹反噬寿元，林渊只敢借一线因果脱身。",
            "word_count": 25,
            "continuity_notes": [],
            "unresolved_threads": [],
        }

    monkeypatch.setattr(rewriter_module.model_gateway, "generate_json", fake_generate_json)

    draft = await rewriter_module.rewriter_service.rewrite_scene_draft(
        db_session,
        organization_id=project.organization_id,
        project_id=project.id,
        job_id=new_id("job"),
        project=project,
        spec=spec,
        chapter=chapter,
        scene=scene,
        current_content="林渊催动完好无损的因果印，轻易逆转生死。",
        issues=[issue],
        target_words=1300,
    )

    prompt = captured["user_prompt"]
    assert draft.content
    assert "## 写作防遗忘承接清单" in prompt
    assert "## 高危问题硬约束" in prompt
    assert "【硬约束/必须修复】" in prompt
    assert "high 严重度问题是硬约束" in prompt
    assert "新稿不得再次触发同类 high 问题" in prompt
    assert f"story_state_item_id={state_id}" in prompt
    assert "关联关键状态" in prompt
    assert "status=damaged" in prompt
    assert "严格遵守“写作防遗忘承接清单”" in prompt
    assert "不要在正文中输出 story_state_item_id" in prompt
    assert captured["metadata"]["linked_story_state_issue_count"] == 1
    assert captured["metadata"]["high_issue_count"] == 1
    assert captured["metadata"]["anti_forgetting_requirement_count"] == 1
