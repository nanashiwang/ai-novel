from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    Chapter,
    ChapterStateRequirement,
    Project,
    StoryStateItem,
)
from app.models.common import new_id
from app.services.story_state.service import StoryStateInput, story_state_service


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
