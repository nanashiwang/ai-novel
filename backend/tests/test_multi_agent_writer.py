"""Sprint 14-C3 多 agent 场景写作测试。

覆盖目标：
1. multi 模式下 writer_service.write_scene_draft 走 planner → drafter → stylist
   三步流水线，最终包装回 SceneDraftContract，且 model_calls 表里能看到 3 条
   带 pipeline_step 标记的记录
2. single 模式回归：默认 settings.writer_pipeline_mode="single"，model_calls 仍然
   只有 1 条 write_scene_draft 记录（标记 pipeline_step="single"），其它流程不变
3. multi 模式 + style_guide 为空：stylist 走 noop 分支，不会产生 polish 的
   model_call（验证 noop 优化）
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import (
    Chapter,
    Character,
    NovelSpec,
    Organization,
    Project,
    Scene,
    User,
)
from app.models.common import new_id
from app.models.model_call import ModelCall
from app.schemas.story_generation import (
    BeatItem,
    BeatSheetContract,
    SceneDraftContract,
)
from app.services.writer.service import writer_service


async def _create_org_project_chapter_scene(
    db_session,
    *,
    style_guide: str = "克制冷峻，多用短句和动作画面。",
) -> tuple[Organization, Project, NovelSpec, Chapter, Scene]:
    user_id = new_id("user")
    db_session.add(
        User(
            id=user_id,
            email=f"{user_id}@example.com",
            display_name="测试用户",
            password_hash="x",
        )
    )

    org_id = new_id("org")
    org = Organization(
        id=org_id,
        name="测试组织",
        owner_user_id=user_id,
        plan_code="Pro",
    )
    db_session.add(org)

    project_id = new_id("project")
    project = Project(
        id=project_id,
        organization_id=org_id,
        title="多 agent 测试项目",
        target_chapter_count=3,
        target_word_count=30000,
        status="scenes_planned",
        created_by=user_id,
    )
    db_session.add(project)

    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="测试前提",
        theme="测试主题",
        genre="奇幻",
        style_guide=style_guide,
    )
    db_session.add(spec)

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="第一章",
        summary="开局摘要",
        goal="建立世界观",
        conflict="主角面对未知",
        ending_hook="留下悬念",
        status="planned",
    )
    db_session.add(chapter)

    scene = Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="开场场景",
        time_marker="清晨",
        location="档案馆",
        characters=["林澈"],
        goal="进入档案室",
        conflict="门禁失效",
        emotion_start="平静",
        emotion_end="警觉",
        reveal="档案被人篡改",
        hook="找到陌生符号",
        status="planned",
    )
    db_session.add(scene)

    db_session.add(
        Character(
            id=new_id("char"),
            organization_id=org_id,
            project_id=project_id,
            name="林澈",
            role="protagonist",
            description="档案员。",
            personality="克制敏锐。",
            motivation="追查真相。",
            secret="接触过核心样本。",
            arc="主动承担代价。",
            relationships={},
            current_state={"status": "准备进入档案馆"},
        )
    )

    await db_session.commit()
    return org, project, spec, chapter, scene


@pytest.mark.asyncio
async def test_multi_agent_writer_produces_three_model_calls(db_session, monkeypatch):
    """multi 模式：planner → drafter → stylist 三步都各写一条 model_calls。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "writer_pipeline_mode", "multi")

    org, project, spec, chapter, scene = await _create_org_project_chapter_scene(
        db_session,
        style_guide="克制冷峻，多用短句和动作画面。",
    )
    job_id = new_id("job")

    draft = await writer_service.write_scene_draft(
        db_session,
        organization_id=org.id,
        project_id=project.id,
        job_id=job_id,
        project=project,
        spec=spec,
        chapter=chapter,
        scene=scene,
        previous_scene_excerpt="",
        target_words=1200,
    )

    assert isinstance(draft, SceneDraftContract)
    assert draft.scene_id == scene.id
    assert draft.content.strip(), "multi 模式必须返回非空正文"
    assert draft.word_count > 0
    assert any("multi-agent pipeline" in note for note in draft.continuity_notes)

    # 校验 model_calls：应有 3 条，分别对应 planner / drafter / stylist
    calls = (
        await db_session.execute(
            select(ModelCall)
            .where(ModelCall.job_id == job_id)
            .order_by(ModelCall.created_at)
        )
    ).scalars().all()
    assert len(calls) == 3, f"multi 模式应记录 3 次 model_call，实际 {len(calls)}"

    steps = [
        (c.metadata_json or {}).get("pipeline_step") for c in calls
    ]
    assert steps == ["planner", "drafter", "stylist"], (
        f"pipeline_step 顺序应为 planner→drafter→stylist，实际 {steps}"
    )

    task_types = {c.task_type for c in calls}
    assert task_types == {
        "write_scene_plan_beats",
        "write_scene_draft_text",
        "write_scene_polish",
    }


@pytest.mark.asyncio
async def test_single_mode_writer_unchanged(db_session, monkeypatch):
    """single 模式回归：保持原行为，只有 1 条 write_scene_draft model_call。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "writer_pipeline_mode", "single")

    org, project, spec, chapter, scene = await _create_org_project_chapter_scene(
        db_session,
    )
    job_id = new_id("job")

    draft = await writer_service.write_scene_draft(
        db_session,
        organization_id=org.id,
        project_id=project.id,
        job_id=job_id,
        project=project,
        spec=spec,
        chapter=chapter,
        scene=scene,
        previous_scene_excerpt="",
        target_words=1200,
    )

    assert isinstance(draft, SceneDraftContract)
    assert draft.scene_id == scene.id
    assert draft.content.strip()

    calls = (
        await db_session.execute(
            select(ModelCall).where(ModelCall.job_id == job_id)
        )
    ).scalars().all()
    assert len(calls) == 1
    assert calls[0].task_type == "write_scene_draft"
    assert (calls[0].metadata_json or {}).get("pipeline_step") == "single"


@pytest.mark.asyncio
async def test_multi_mode_stylist_noop_when_style_guide_empty(db_session, monkeypatch):
    """multi 模式 + style_guide 为空：stylist 走 noop，只记 2 条 model_call。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "writer_pipeline_mode", "multi")

    org, project, spec, chapter, scene = await _create_org_project_chapter_scene(
        db_session,
        style_guide="",
    )
    job_id = new_id("job")

    draft = await writer_service.write_scene_draft(
        db_session,
        organization_id=org.id,
        project_id=project.id,
        job_id=job_id,
        project=project,
        spec=spec,
        chapter=chapter,
        scene=scene,
        previous_scene_excerpt="",
        target_words=1200,
    )
    assert draft.content.strip()

    calls = (
        await db_session.execute(
            select(ModelCall)
            .where(ModelCall.job_id == job_id)
            .order_by(ModelCall.created_at)
        )
    ).scalars().all()
    steps = [(c.metadata_json or {}).get("pipeline_step") for c in calls]
    # stylist noop 不应该产生 model_call
    assert "stylist" not in steps
    assert steps == ["planner", "drafter"]


@pytest.mark.asyncio
async def test_planner_drafter_stylist_failfast_when_planner_returns_no_beats(
    db_session, monkeypatch
):
    """planner 返回 0 beat：multi 模式应 fail-fast 抛错。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "writer_pipeline_mode", "multi")

    # patch planner 让它返回空 beats
    from app.services.writer import planner as planner_module

    async def _empty_plan_beats(*args, **kwargs):
        return BeatSheetContract(beats=[], total_target_words=0)

    monkeypatch.setattr(
        planner_module.scene_planner_agent,
        "plan_beats",
        _empty_plan_beats,
    )

    org, project, spec, chapter, scene = await _create_org_project_chapter_scene(
        db_session,
    )
    job_id = new_id("job")

    with pytest.raises(ValueError, match="scene_planner_returned_no_beats"):
        await writer_service.write_scene_draft(
            db_session,
            organization_id=org.id,
            project_id=project.id,
            job_id=job_id,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            previous_scene_excerpt="",
            target_words=1200,
        )


@pytest.mark.asyncio
async def test_beat_sheet_contract_normalizes_target_words():
    """BeatItem.target_words 接受字符串数字并兜底下限 50。"""
    sheet = BeatSheetContract.model_validate(
        {
            "beats": [
                {
                    "index": 1,
                    "purpose": "开场",
                    "action": "测试",
                    "target_words": "200",
                },
                {
                    "index": 2,
                    "purpose": "结尾",
                    "action": "测试",
                    "target_words": 0,  # 兜底成 50
                },
            ],
            "total_target_words": "1200",
        }
    )
    assert isinstance(sheet.beats[0], BeatItem)
    assert sheet.beats[0].target_words == 200
    assert sheet.beats[1].target_words == 50
    assert sheet.total_target_words == 1200
