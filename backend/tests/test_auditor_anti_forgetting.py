from __future__ import annotations

from typing import Any

import pytest

from app.models import (
    Chapter,
    ChapterStateRequirement,
    NovelSpec,
    Project,
    Scene,
    StoryStateItem,
)
from app.models.common import new_id
from app.services.auditor import service as auditor_module


@pytest.mark.asyncio
async def test_auditor_injects_anti_forgetting_context(db_session, monkeypatch):
    org_id = new_id("org")
    project_id = new_id("project")
    chapter_id = new_id("chapter")
    scene_id = new_id("scene")
    state_id = new_id("state")

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
    db_session.add_all([project, spec, chapter, scene, state, requirement])
    await db_session.commit()

    captured: dict[str, Any] = {}

    async def fake_generate_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured["user_prompt"] = kwargs["user_prompt"]
        captured["metadata"] = kwargs["metadata"]
        return {
            "issues": [
                {
                    "issue_type": "设定冲突",
                    "severity": "高",
                    "description": "正文把因果印写成完好无损，与关键状态冲突。",
                    "suggested_fix": "把催动因果印前的描写改为裂痕反噬，并补一句代价。",
                    "story_state_item_id": state_id,
                }
            ]
        }

    monkeypatch.setattr(auditor_module.model_gateway, "generate_json", fake_generate_json)

    result = await auditor_module.auditor_service.audit_scene_draft(
        db_session,
        organization_id=org_id,
        project_id=project_id,
        job_id=new_id("job"),
        project=project,
        spec=spec,
        chapter=chapter,
        scene=scene,
        draft_content="林渊抬手一按，完好无损的因果印立刻逆转生死。",
    )

    assert result.issues[0].issue_type == "state_conflict"
    assert result.issues[0].severity == "high"
    assert result.issues[0].story_state_item_id == state_id
    assert "## 防遗忘审稿清单" in captured["user_prompt"]
    assert "本章承接要求" in captured["user_prompt"]
    assert state_id in captured["user_prompt"]
    assert "因果印已有裂痕" in captured["user_prompt"]
    assert "premature_state_use" in captured["user_prompt"]
    assert "resolved_state_reused" in captured["user_prompt"]
    assert captured["metadata"]["anti_forgetting_state_count"] >= 1
    assert captured["metadata"]["anti_forgetting_requirement_count"] == 1
