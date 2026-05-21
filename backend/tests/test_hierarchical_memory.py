"""Sprint 14-C2：分层摘要记忆 L1-L4 测试。

覆盖：
- 写入 L1 (scene_plan) 后 summarize_chapter 产出 L2，落库字段正确；
- 多章 L2 → summarize_volume 产出 L3；多卷 L3 → summarize_book 产出 L4；
- LLM 异常时走 fallback，仍能落库；
- ContextBuilder.build_for_scene_planning 注入 recent_scenes / arc_summaries 段；
- 空数据时 to_prompt 不输出标题。
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Chapter, MemoryEntry, NovelSpec, Project, Scene, Volume
from app.models.common import new_id
from app.services.context_builder import ContextBuilder
from app.services.memory.summarizer import hierarchical_summarizer


async def _seed_project(db_session) -> tuple[str, str, NovelSpec, Project]:
    org_id = new_id("org")
    project_id = new_id("project")
    project = Project(
        id=project_id,
        organization_id=org_id,
        created_by="user_x",
        title="弧线摘要测试",
        genre="奇幻",
        target_word_count=100000,
        target_chapter_count=10,
        language="zh-CN",
        style="冷峻",
        status="outlined",
        cover_url="",
        tags=[],
        target_reader="—",
    )
    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="主角寻找失落的城",
        theme="代价",
        genre="奇幻",
        tone="紧张",
        target_reader="—",
        narrative_pov="第三人称",
        style_guide="画面优先",
        constraints=["保持视角一致"],
        continuity_rules=[],
    )
    db_session.add_all([project, spec])
    await db_session.commit()
    return org_id, project_id, spec, project


def _make_scene(*, org_id: str, project_id: str, chapter_id: str, idx: int) -> Scene:
    return Scene(
        id=new_id("scene"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter_id,
        scene_index=idx,
        title=f"第 {idx} 场",
        time_marker="—",
        location="—",
        characters=[],
        goal=f"目标 {idx}",
        conflict=f"冲突 {idx}",
        emotion_start="—",
        emotion_end="—",
        reveal=f"揭示 {idx}",
        hook=f"钩子 {idx}",
        status="planned",
    )


def _make_chapter(
    *, org_id: str, project_id: str, idx: int, volume_id: str | None = None
) -> Chapter:
    return Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=volume_id,
        chapter_index=idx,
        title=f"第 {idx} 章",
        summary=f"章 {idx} 摘要",
        goal=f"章 {idx} 目标",
        conflict=f"章 {idx} 冲突",
        ending_hook=f"章 {idx} 钩子",
        status="planned",
    )


def _make_l1(
    *, org_id: str, project_id: str, scene_id: str, chapter_idx: int, content: str
) -> MemoryEntry:
    return MemoryEntry(
        id=new_id("mem_entry"),
        organization_id=org_id,
        project_id=project_id,
        source_type="scene",
        source_id=scene_id,
        memory_type="scene_plan",
        title=f"场景摘要 {scene_id[-4:]}",
        content=content,
        importance=3,
        level="L1",
        arc_window=f"ch{chapter_idx}",
    )


@pytest.mark.asyncio
async def test_summarize_chapter_produces_l2_entry(db_session):
    """聚合单章 L1 → 1 条 L2，arc_window=chX。"""
    org_id, project_id, _spec, _project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=1)
    scenes = [
        _make_scene(org_id=org_id, project_id=project_id, chapter_id=chapter.id, idx=i)
        for i in range(1, 4)
    ]
    db_session.add(chapter)
    db_session.add_all(scenes)
    for scene in scenes:
        db_session.add(
            _make_l1(
                org_id=org_id,
                project_id=project_id,
                scene_id=scene.id,
                chapter_idx=1,
                content=f"场景 {scene.scene_index} 的关键信息：主角推进调查。",
            )
        )
    await db_session.commit()

    entry = await hierarchical_summarizer.summarize_chapter(
        db_session,
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
    )
    assert entry is not None
    assert entry.level == "L2"
    assert entry.arc_window == "ch1"
    assert entry.source_type == "chapter"
    assert entry.source_id == chapter.id
    assert entry.memory_type == "arc_summary"
    assert entry.content.strip()


@pytest.mark.asyncio
async def test_summarize_chapter_returns_none_when_no_l1(db_session):
    """没有 L1 时不写空 L2。"""
    org_id, project_id, _spec, _project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=1)
    db_session.add(chapter)
    await db_session.commit()

    entry = await hierarchical_summarizer.summarize_chapter(
        db_session,
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
    )
    assert entry is None


@pytest.mark.asyncio
async def test_summarize_volume_aggregates_l2_to_l3(db_session):
    """卷下两章 L2 → 1 条 L3，arc_window 覆盖完整 chapter 范围。"""
    org_id, project_id, _spec, _project = await _seed_project(db_session)
    volume = Volume(
        id=new_id("volume"),
        organization_id=org_id,
        project_id=project_id,
        volume_index=1,
        title="第一卷",
        summary="",
        goal="揭开身世",
        status="planned",
    )
    chapters = [
        _make_chapter(
            org_id=org_id, project_id=project_id, idx=i, volume_id=volume.id
        )
        for i in (1, 2)
    ]
    db_session.add(volume)
    db_session.add_all(chapters)
    for chapter in chapters:
        db_session.add(
            MemoryEntry(
                id=new_id("mem_entry"),
                organization_id=org_id,
                project_id=project_id,
                source_type="chapter",
                source_id=chapter.id,
                memory_type="arc_summary",
                title=f"第 {chapter.chapter_index} 章弧线摘要",
                content=f"章 {chapter.chapter_index} 弧线：主角推进剧情。",
                importance=4,
                level="L2",
                arc_window=f"ch{chapter.chapter_index}",
            )
        )
    await db_session.commit()

    entry = await hierarchical_summarizer.summarize_volume(
        db_session,
        organization_id=org_id,
        project_id=project_id,
        volume_id=volume.id,
    )
    assert entry is not None
    assert entry.level == "L3"
    assert entry.source_type == "volume"
    assert "ch1-ch2" in (entry.arc_window or "")
    assert entry.content.strip()


@pytest.mark.asyncio
async def test_summarize_book_falls_back_to_l2_when_no_l3(db_session):
    """没有任何 L3 时 summarize_book 用 L2 全集回落，仍能产出 L4。"""
    org_id, project_id, _spec, _project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=1)
    db_session.add(chapter)
    db_session.add(
        MemoryEntry(
            id=new_id("mem_entry"),
            organization_id=org_id,
            project_id=project_id,
            source_type="chapter",
            source_id=chapter.id,
            memory_type="arc_summary",
            title="第 1 章弧线摘要",
            content="主角踏上旅程。",
            importance=4,
            level="L2",
            arc_window="ch1",
        )
    )
    await db_session.commit()

    entry = await hierarchical_summarizer.summarize_book(
        db_session,
        organization_id=org_id,
        project_id=project_id,
    )
    assert entry is not None
    assert entry.level == "L4"
    assert entry.arc_window == "book"
    assert entry.source_id == project_id


@pytest.mark.asyncio
async def test_summarize_chapter_fallback_on_llm_failure(db_session, monkeypatch):
    """LLM 抛错时落到 fallback，不阻断主流程，仍写入 L2。"""
    org_id, project_id, _spec, _project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=2)
    scene = _make_scene(org_id=org_id, project_id=project_id, chapter_id=chapter.id, idx=1)
    db_session.add(chapter)
    db_session.add(scene)
    db_session.add(
        _make_l1(
            org_id=org_id,
            project_id=project_id,
            scene_id=scene.id,
            chapter_idx=2,
            content="关键线索：神秘符号出现在墙上。",
        )
    )
    await db_session.commit()

    from app.services.model_gateway.service import model_gateway as gw

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_llm_failure")

    monkeypatch.setattr(gw, "generate_text", _boom)

    entry = await hierarchical_summarizer.summarize_chapter(
        db_session,
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
    )
    assert entry is not None
    assert entry.level == "L2"
    # fallback 拼接了原 L1 的关键词
    assert "神秘符号" in entry.content


@pytest.mark.asyncio
async def test_context_builder_injects_arc_summaries(db_session):
    """build_for_scene_planning 注入 recent_scenes + arc_summaries 段。"""
    org_id, project_id, spec, project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=3)
    scene = _make_scene(org_id=org_id, project_id=project_id, chapter_id=chapter.id, idx=1)
    db_session.add(chapter)
    db_session.add(scene)
    # 1 条 L1 喂 recent_scenes
    db_session.add(
        _make_l1(
            org_id=org_id,
            project_id=project_id,
            scene_id=scene.id,
            chapter_idx=3,
            content="主角抵达旧城门口。",
        )
    )
    # 1 条 L2 + 1 条 L4 喂 arc_summaries
    db_session.add(
        MemoryEntry(
            id=new_id("mem_entry"),
            organization_id=org_id,
            project_id=project_id,
            source_type="chapter",
            source_id=chapter.id,
            memory_type="arc_summary",
            title="第 1 章弧线摘要",
            content="第一章：主角接到任务并启程。",
            importance=4,
            level="L2",
            arc_window="ch1",
        )
    )
    db_session.add(
        MemoryEntry(
            id=new_id("mem_entry"),
            organization_id=org_id,
            project_id=project_id,
            source_type="book",
            source_id=project_id,
            memory_type="arc_summary",
            title="整书弧线摘要",
            content="整书：主角追寻失落之城并付出代价。",
            importance=6,
            level="L4",
            arc_window="book",
        )
    )
    await db_session.commit()

    builder = ContextBuilder(total_budget=4000)
    ctx = await builder.build_for_scene_planning(
        db_session, project=project, spec=spec, chapter=chapter
    )
    labels = [s.label for s in ctx.segments]
    assert "recent_scenes" in labels
    assert "arc_summaries" in labels

    recent = next(s for s in ctx.segments if s.label == "recent_scenes")
    arcs = next(s for s in ctx.segments if s.label == "arc_summaries")
    assert recent.trusted is True
    assert arcs.trusted is True
    assert "旧城门口" in recent.content
    # arc_summaries 顺序：L4 在 L2 之前
    assert "整书" in arcs.content
    assert "[L4|book]" in arcs.content
    assert "[L2|ch1]" in arcs.content
    assert arcs.content.index("整书") < arcs.content.index("第一章")

    prompt = ctx.to_prompt()
    assert "[recent_scenes]" in prompt
    assert "[arc_summaries]" in prompt


@pytest.mark.asyncio
async def test_context_builder_skips_empty_arc_section(db_session):
    """没有任何 L2/L3/L4 时 arc_summaries 段被自动跳过。"""
    org_id, project_id, spec, project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=1)
    db_session.add(chapter)
    await db_session.commit()

    builder = ContextBuilder(total_budget=4000)
    ctx = await builder.build_for_scene_planning(
        db_session, project=project, spec=spec, chapter=chapter
    )
    prompt = ctx.to_prompt()
    assert "[arc_summaries]" not in prompt
    assert "[recent_scenes]" not in prompt


def test_segment_budget_sums_to_one():
    """硬约束：budget 必须严格加到 1.0。"""
    from app.services.context_builder.service import _SEGMENT_BUDGET_PCT

    assert abs(sum(_SEGMENT_BUDGET_PCT.values()) - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_record_scene_memory_marks_l1(db_session):
    """ContextBuilder.record_scene_memory 必须把 level 写成 L1。"""
    org_id, project_id, _spec, _project = await _seed_project(db_session)
    chapter = _make_chapter(org_id=org_id, project_id=project_id, idx=1)
    scene = _make_scene(
        org_id=org_id, project_id=project_id, chapter_id=chapter.id, idx=1
    )
    db_session.add(chapter)
    db_session.add(scene)
    await db_session.commit()

    builder = ContextBuilder(total_budget=2000)
    await builder.record_scene_memory(
        db_session,
        organization_id=org_id,
        project_id=project_id,
        scene=scene,
        chapter=chapter,
    )
    await db_session.commit()

    rows = list(
        (
            await db_session.execute(
                select(MemoryEntry).where(MemoryEntry.source_id == scene.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].level == "L1"
    assert rows[0].arc_window == "ch1"
