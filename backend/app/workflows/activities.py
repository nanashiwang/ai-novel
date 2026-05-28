"""Temporal Activities。

工作流只编排步骤；所有模型调用、数据库写入都放在 activity 内。
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from app.contracts import MAX_OUTLINE_CHAPTERS, OUTLINE_CHAPTER_BATCH_SIZE
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import NotFoundError
from app.core.metrics import JOBS_CREATED
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.continuity_issue import ContinuityIssue
from app.models.draft_version import DraftVersion
from app.models.generation_job import GenerationJob
from app.models.memory import MemoryEntry
from app.models.plot_thread import PlotThread
from app.models.project import NovelSpec, Project
from app.models.quota import QuotaReservation
from app.models.scene import Scene
from app.models.world_item import WorldItem
from app.repositories import (
    ChapterRepository,
    CharacterRepository,
    ContinuityIssueRepository,
    DraftVersionRepository,
    GenerationJobRepository,
    NovelSpecRepository,
    PlotThreadRepository,
    ProjectRepository,
    RevisionMessageRepository,
    RevisionProposalRepository,
    RevisionSessionRepository,
    SceneRepository,
    UsageEventRepository,
    WorldItemRepository,
)
from app.schemas.story_generation import StoryBibleContract
from app.services.auditor.service import auditor_service
from app.services.context_builder.service import context_builder
from app.services.event_bus import build_event, publish_event_fire_and_forget
from app.services.ledger import ledger_service
from app.services.memory import memory_service
from app.services.model_gateway.service import model_gateway
from app.services.moderation import log_moderation_event, moderation_service
from app.services.novel_planner.service import novel_planner_service
from app.services.quota.service import quota_service
from app.services.rewriter.service import rewriter_service
from app.services.writer.service import writer_service

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def _activity_session() -> AsyncIterator[AsyncSession]:
    """Activity 内的统一 session 边界。

    用法：
        @activity.defn(name="xxx")
        async def my_activity(...):
            async with _activity_session() as session:
                # 业务逻辑；正常退出 commit，异常退出 rollback。
                ...

    比之前的 `await _with_session(handler)` 闭包模式少一层嵌套，
    并且符合 Python 异步上下文的常规直觉。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _load_job(session: AsyncSession, job_id: str) -> GenerationJob:
    job = await GenerationJobRepository(session).get(job_id)
    if not job:
        raise NotFoundError("job_not_found")
    return job


async def _load_project(session: AsyncSession, job: GenerationJob) -> Project:
    project = await ProjectRepository(session).get(
        job.project_id,
        organization_id=job.organization_id,
    )
    if not project:
        raise NotFoundError("project_not_found")
    return project


async def _load_spec(session: AsyncSession, job: GenerationJob) -> NovelSpec:
    spec = await NovelSpecRepository(session).get_by(
        organization_id=job.organization_id,
        project_id=job.project_id,
    )
    if not spec:
        raise NotFoundError("novel_spec_not_found")
    return spec


def _contract_constraints(bible) -> list[str]:
    """保留 StoryBibleContract.constraints 原值。

    历史上这里还会把 world_rules / continuity_rules / main_characters 折叠
    成中文字符串塞进 constraints。问题是这些信息其他地方已有结构化存储：
    - locations / factions / world_rules → world_items 表
    - continuity_rules → NovelSpec.continuity_rules（独立 JSON 列）
    - main_characters → characters 表

    折叠后 ContextBuilder 想精确读取某条规则需要做字符串解析，可靠性差。
    现在只透传 constraints 本身；其他字段由 generate_book_spec 各自写入
    对应表/列。
    """
    return list(bible.constraints or [])


def _payload_int(payload: dict[str, Any], key: str, default: int) -> int:
    """从 payload 取 int 字段，None/缺失/无法转换时回落到 default。

    与 `payload.get(key) or default` 不同：用户显式传入 0 时返回 0，而不会
    被 falsy 判定替换成 default。
    """
    value = payload.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_moderation_tasks: set[Any] = set()


def _spawn_moderation_check(
    text: str,
    *,
    organization_id: str,
    project_id: str,
    scene_id: str | None,
    source: str,
) -> None:
    """Fire-and-forget 内容审查。不阻断主流程；高风险结果只记日志。

    任务 set 持有引用避免 GC 提前回收，参考 Python 官方 asyncio 文档。
    """
    if not text:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return  # 没有运行 loop 时直接放弃（测试/local 路径偶现）

    async def _run() -> None:
        try:
            result = await moderation_service.check(text)
            log_moderation_event(
                result,
                organization_id=organization_id,
                project_id=project_id,
                scene_id=scene_id,
                source=source,
            )
        except Exception:  # noqa: BLE001
            _logger.warning("moderation_check_failed", exc_info=True)

    task = loop.create_task(_run())
    _moderation_tasks.add(task)
    task.add_done_callback(_moderation_tasks.discard)


async def _run_ledger_check(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    scene_id: str,
    draft_content: str,
    source: str,
) -> None:
    """同步运行信息释放校验（Sprint 14-C5）。

    与 moderation 不同，ledger 校验需要读 db；为了避免和主 session 抢
    SQLite 单连接锁（in-memory 测试场景常见），这里直接复用主 session
    而不是 fire-and-forget 新 session。复用主 session 是 read-only 的，
    主流程的 SQL 写入已经在前面完成，无副作用。

    任何异常都被 swallow + warn，绝不影响 scene 写作的 commit 路径。
    """
    if not draft_content or not scene_id:
        return
    try:
        scene = await SceneRepository(session).get(
            scene_id, organization_id=organization_id
        )
        if not scene:
            return
        violations = await ledger_service.validate_reveal(
            session,
            project_id=project_id,
            scene=scene,
            draft_content=draft_content,
        )
        for v in violations:
            _logger.warning(
                "ledger_violation",
                extra={
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "source": source,
                    "fact_id": v.fact_id,
                    "severity": v.severity,
                    "description": v.description,
                },
            )
    except Exception:  # noqa: BLE001
        _logger.warning("ledger_check_failed", exc_info=True)


async def _run_chapter_in_extracts(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    job_id: str | None,
    chapter: Chapter,
    scene: Scene,
    draft: DraftVersion,
    created_by: str | None,
) -> None:
    """Sprint 16-E4：章内同步等待 character/world/plot 三链推演落库。

    与单 scene WriteSceneWorkflow 已有的等待逻辑对齐——批量模式
    （write_scene_drafts / write_chapter_scenes_for_full_novel）之前完全没跑
    character_revisions / world_item_revisions / plot_thread_revisions
    extract，下一 scene 看不到推演结果。这里复用主 session 同步跑，让同章
    后续 scene 写作能立刻看到上一场的推演产出（pending 状态，用户审核后
    才会通过 ContextBuilder world_actions / plot_actions 段进入下一章 prompt）。

    任何异常都 swallow + warn，绝不阻断写作主流程。
    """
    if not draft or not draft.content:
        return
    try:
        from app.services.character_tracker.extract import (  # noqa: PLC0415
            extract_state_changes_from_scene as _extract_char,
        )

        await _extract_char(
            session,
            organization_id=organization_id,
            project_id=project_id,
            scene_id=scene.id,
            scene_content=draft.content,
            created_by=created_by or "system",
        )
    except Exception:  # noqa: BLE001
        _logger.warning("inchapter_character_extract_failed", exc_info=True)

    try:
        from app.services.world_tracker.extract import (  # noqa: PLC0415
            extract_world_changes_from_scene as _extract_world,
        )

        await _extract_world(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            chapter=chapter,
            scene=scene,
            draft=draft,
        )
    except Exception:  # noqa: BLE001
        _logger.warning("inchapter_world_extract_failed", exc_info=True)

    try:
        from app.services.plot_thread_tracker.extract import (  # noqa: PLC0415
            extract_plot_thread_changes_from_scene as _extract_plot,
        )

        await _extract_plot(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            chapter=chapter,
            scene=scene,
            draft=draft,
        )
    except Exception:  # noqa: BLE001
        _logger.warning("inchapter_plot_extract_failed", exc_info=True)

    try:
        from app.services.story_state.extract import (  # noqa: PLC0415
            extract_story_state_from_scene as _extract_story_state,
        )

        await _extract_story_state(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            chapter=chapter,
            scene=scene,
            draft=draft,
            created_by=created_by,
        )
    except Exception:  # noqa: BLE001
        _logger.warning("inchapter_story_state_extract_failed", exc_info=True)

    # Sprint 17-B 全局时间线：同步推演结构化时间戳并写回 scenes 表。
    try:
        from app.services.temporal_tracker.extract import (  # noqa: PLC0415
            extract_temporal_state_from_scene as _extract_temporal,
        )

        await _extract_temporal(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            chapter=chapter,
            scene=scene,
            draft=draft,
        )
    except Exception:  # noqa: BLE001
        _logger.warning("inchapter_temporal_extract_failed", exc_info=True)


_summarize_tasks: set[Any] = set()


def _spawn_chapter_summarize(
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
    source: str,
) -> None:
    """Fire-and-forget 章节摘要（Sprint 16-E5）。

    write_scene_drafts / write_chapter_scenes_for_full_novel 在本章全部 scene
    都 drafted 时调用；走独立 session 跑 hierarchical_summarizer.summarize_chapter，
    产 L2 摘要后续供 ContextBuilder arc_summaries 段召回。任何失败 swallow + warn。
    """
    if not chapter_id:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            from app.services.memory.summarizer import (  # noqa: PLC0415
                hierarchical_summarizer,
            )

            async with AsyncSessionLocal() as session:
                await hierarchical_summarizer.summarize_chapter(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "chapter_summarize_failed",
                exc_info=True,
                extra={"chapter_id": chapter_id, "source": source},
            )

    task = loop.create_task(_run())
    _summarize_tasks.add(task)
    task.add_done_callback(_summarize_tasks.discard)


def _spawn_arc_summarize(
    *,
    organization_id: str,
    project_id: str,
    start_chapter_index: int,
    end_chapter_index: int,
    source: str,
) -> None:
    """Sprint 17-A 防漂移：fire-and-forget 每 10 章触发 L3 弧线摘要。

    用于 ContextBuilder 的"距离衰减"召回：中距离（11-50 章）章节将优先
    读 L3 弧摘而非 L2 全文，控制 token 增长。失败 swallow + warn。
    """
    if end_chapter_index < start_chapter_index:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            from app.services.memory.summarizer import (  # noqa: PLC0415
                hierarchical_summarizer,
            )

            async with AsyncSessionLocal() as session:
                await hierarchical_summarizer.summarize_arc(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    start_chapter_index=start_chapter_index,
                    end_chapter_index=end_chapter_index,
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "arc_summarize_failed",
                exc_info=True,
                extra={
                    "start": start_chapter_index,
                    "end": end_chapter_index,
                    "source": source,
                },
            )

    task = loop.create_task(_run())
    _summarize_tasks.add(task)
    task.add_done_callback(_summarize_tasks.discard)


def _spawn_character_milestones(
    *,
    organization_id: str,
    project_id: str,
    chapter_index: int,
    source: str,
) -> None:
    """Sprint 17-A 防漂移：fire-and-forget 给项目所有角色生成 milestone 快照。"""
    if chapter_index <= 0:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            from app.services.character_tracker.milestone import (  # noqa: PLC0415
                create_milestones_for_project,
            )

            async with AsyncSessionLocal() as session:
                await create_milestones_for_project(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter_index=chapter_index,
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "character_milestones_failed",
                exc_info=True,
                extra={"chapter_index": chapter_index, "source": source},
            )

    task = loop.create_task(_run())
    _summarize_tasks.add(task)
    task.add_done_callback(_summarize_tasks.discard)


def _spawn_long_range_audit(
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
    source: str,
) -> None:
    """Sprint 17-A 防漂移：fire-and-forget 对该章最后一个 drafted scene 做
    long_range_continuity 审计（每 20 章触发一次）。失败 swallow + warn。"""
    if not chapter_id:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            from app.services.auditor.service import auditor_service  # noqa: PLC0415

            async with AsyncSessionLocal() as session:
                chapter = await ChapterRepository(session).get(
                    chapter_id, organization_id=organization_id
                )
                if not chapter:
                    return
                scenes = list(
                    await SceneRepository(session).list(
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter_id=chapter_id,
                        order_by=Scene.scene_index.desc(),
                    )
                )
                if not scenes:
                    return
                target_scene = scenes[0]
                latest_draft_id = await _latest_draft_id(session, target_scene)
                if not latest_draft_id:
                    return
                draft = await DraftVersionRepository(session).get(
                    latest_draft_id, organization_id=organization_id
                )
                if not draft:
                    return
                project = await ProjectRepository(session).get(
                    project_id, organization_id=organization_id
                )
                spec = await NovelSpecRepository(session).get_by(
                    organization_id=organization_id, project_id=project_id
                )
                if not project or not spec:
                    return
                contract = await auditor_service.audit_scene_draft(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    job_id=f"long_range_audit_{chapter_id}",
                    project=project,
                    spec=spec,
                    chapter=chapter,
                    scene=target_scene,
                    draft_content=draft.content,
                    mode="long_range",
                )
                issue_repo = ContinuityIssueRepository(session)
                for item in contract.issues:
                    await issue_repo.create(
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter_id=chapter_id,
                        scene_id=target_scene.id,
                        issue_type=item.issue_type,
                        severity=item.severity,
                        description=item.description,
                        suggested_fix=item.suggested_fix,
                        status="open",
                    )
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "long_range_audit_failed",
                exc_info=True,
                extra={"chapter_id": chapter_id, "source": source},
            )

    task = loop.create_task(_run())
    _summarize_tasks.add(task)
    task.add_done_callback(_summarize_tasks.discard)


def _spawn_style_drift_check(
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
    chapter_index: int,
    source: str,
) -> None:
    """Sprint 17-A 防漂移：fire-and-forget 每 100 章对比对白 embedding 距离。"""
    if chapter_index <= 0 or not chapter_id:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            from app.services.auditor.style_drift import (  # noqa: PLC0415
                check_style_drift,
            )

            async with AsyncSessionLocal() as session:
                await check_style_drift(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    current_chapter_index=chapter_index,
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "style_drift_check_failed",
                exc_info=True,
                extra={"chapter_id": chapter_id, "source": source},
            )

    task = loop.create_task(_run())
    _summarize_tasks.add(task)
    task.add_done_callback(_summarize_tasks.discard)


def _spawn_chapter_polish(
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
    user_id: str | None,
    source: str,
) -> None:
    """Sprint 17-C 方案 3：fire-and-forget 触发整章润色 pass。

    默认 settings.chapter_polish_enabled=False；调用方需先判断。失败
    swallow + warn，不阻塞主流程。
    """
    if not chapter_id:
        return
    try:
        import asyncio as _asyncio  # noqa: PLC0415

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            from app.services.polisher import polish_chapter as _do  # noqa: PLC0415

            async with AsyncSessionLocal() as session:
                chapter = await ChapterRepository(session).get(
                    chapter_id, organization_id=organization_id
                )
                if not chapter:
                    return
                project = await ProjectRepository(session).get(
                    chapter.project_id, organization_id=organization_id
                )
                if not project:
                    return
                spec = await NovelSpecRepository(session).get_by(
                    organization_id=organization_id, project_id=project.id
                )
                if not spec:
                    return
                await _do(
                    session,
                    organization_id=organization_id,
                    project_id=project.id,
                    job_id=None,
                    project=project,
                    spec=spec,
                    chapter=chapter,
                    created_by=user_id or "system",
                    force=False,
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "chapter_polish_spawn_failed",
                exc_info=True,
                extra={"chapter_id": chapter_id, "source": source},
            )

    task = loop.create_task(_run())
    _summarize_tasks.add(task)
    task.add_done_callback(_summarize_tasks.discard)


async def _delete_project_rows(
    session: AsyncSession,
    job: GenerationJob,
    model: type,
    **filters: Any,
) -> int:
    stmt = select(model).where(
        model.organization_id == job.organization_id,
        model.project_id == job.project_id,
    )
    for key, value in filters.items():
        if value is None:
            continue
        column = getattr(model, key)
        if isinstance(value, (list, tuple, set, frozenset)):
            values = list(value)
            if not values:
                return 0
            stmt = stmt.where(column.in_(values))
        else:
            stmt = stmt.where(column == value)
    rows = list((await session.execute(stmt)).scalars().all())
    for row in rows:
        await session.delete(row)
    if rows:
        await session.flush()
    return len(rows)


async def _clear_outline_dependents(session: AsyncSession, job: GenerationJob) -> dict[str, int]:
    """清掉由大纲/场景/正文派生出的数据，避免重生成后混用旧设定。"""
    counts: dict[str, int] = {}
    for model, key in [
        (ContinuityIssue, "continuity_issues"),
        (DraftVersion, "draft_versions"),
        (Scene, "scenes"),
        (Chapter, "chapters"),
    ]:
        counts[key] = await _delete_project_rows(session, job, model)
    counts["memory_entries"] = await _delete_project_rows(
        session,
        job,
        MemoryEntry,
        source_type="scene",
    )
    return counts


async def _clear_story_bible_dependents(
    session: AsyncSession,
    job: GenerationJob,
) -> dict[str, int]:
    """重生成故事圣经时，旧人物/世界观/大纲都视为失效。"""
    counts = await _clear_outline_dependents(session, job)
    for model, key in [
        (PlotThread, "plot_threads"),
        (WorldItem, "world_items"),
        (Character, "characters"),
    ]:
        counts[key] = await _delete_project_rows(session, job, model)
    return counts


async def _character_roster_for_prompt(session: AsyncSession, job: GenerationJob) -> str:
    rows = list(
        await CharacterRepository(session).list(
            organization_id=job.organization_id,
            project_id=job.project_id,
            order_by=Character.created_at.asc(),
        )
    )
    if not rows:
        return ""
    lines = []
    for row in rows[:40]:
        details = [row.description, row.personality, row.motivation, row.secret, row.arc]
        detail = "；".join(item for item in details if item)
        lines.append(f"- {row.name}（{row.role or 'supporting'}）：{detail}")
    return "\n".join(lines)


async def _sync_bible_characters(session: AsyncSession, job: GenerationJob, bible) -> int:
    repo = CharacterRepository(session)
    count = 0
    for seed in bible.main_characters or []:
        name = (seed.name or "").strip()
        if not name:
            continue
        existing = await repo.get_by(
            organization_id=job.organization_id,
            project_id=job.project_id,
            name=name,
        )
        values = {
            "role": seed.role or "supporting",
            "description": seed.description,
            "personality": seed.personality,
            "motivation": seed.motivation,
            "secret": seed.secret,
            "arc": seed.arc,
            "relationships": seed.relationships,
            "current_state": seed.current_state,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            await repo.create(
                organization_id=job.organization_id,
                project_id=job.project_id,
                name=name,
                **values,
            )
        count += 1
    return count


async def _sync_bible_world_items(session: AsyncSession, job: GenerationJob, bible) -> int:
    repo = WorldItemRepository(session)
    count = 0

    async def upsert_item(
        *,
        item_type: str,
        name: str,
        description: str,
        importance: str = "medium",
        is_hard_rule: bool = False,
    ) -> None:
        nonlocal count
        clean_name = name.strip()[:200]
        clean_description = description.strip()
        if not clean_name and not clean_description:
            return
        clean_name = clean_name or clean_description[:80] or "未命名设定"
        existing = await repo.get_by(
            organization_id=job.organization_id,
            project_id=job.project_id,
            type=item_type,
            name=clean_name,
        )
        values = {
            "type": item_type,
            "description": clean_description or clean_name,
            "rules": {"source": "story_bible", "kind": item_type},
            "related_characters": [],
            "importance": importance or "medium",
            "is_hard_rule": is_hard_rule,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            await repo.create(
                organization_id=job.organization_id,
                project_id=job.project_id,
                name=clean_name,
                **values,
            )
        count += 1

    for index, location in enumerate(getattr(bible, "locations", []) or [], start=1):
        name = getattr(location, "name", "") or f"重要地点 {index}"
        description = getattr(location, "description", "") or str(name)
        importance = getattr(location, "importance", "medium")
        await upsert_item(
            item_type="location",
            name=str(name),
            description=str(description),
            importance=str(importance),
        )

    for index, faction in enumerate(getattr(bible, "factions", []) or [], start=1):
        name = getattr(faction, "name", "") or f"关键势力 {index}"
        description = getattr(faction, "description", "") or str(name)
        importance = getattr(faction, "importance", "medium")
        await upsert_item(
            item_type="faction",
            name=str(name),
            description=str(description),
            importance=str(importance),
        )

    for index, rule in enumerate(bible.world_rules or [], start=1):
        text = str(rule).strip()
        if not text:
            continue
        name = text[:80] or f"世界规则 {index}"
        await upsert_item(
            item_type="rule",
            name=name,
            description=text,
            importance="high",
            is_hard_rule=True,
        )
    return count


async def _sync_bible_plot_threads(session: AsyncSession, job: GenerationJob, bible) -> int:
    repo = PlotThreadRepository(session)
    threads = list(bible.plot_threads or [])
    if not threads:
        fallback = bible.theme or bible.premise
        if fallback:
            threads = [fallback]
    count = 0
    for index, thread in enumerate(threads, start=1):
        title = str(thread).strip()
        if not title:
            continue
        existing = await repo.get_by(
            organization_id=job.organization_id,
            project_id=job.project_id,
            title=title[:200],
        )
        values = {
            "thread_type": "main" if index == 1 else "subplot",
            "description": title,
            "status": "open",
            "related_characters": [],
            "opened_at_scene_id": None,
            "closed_at_scene_id": None,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            await repo.create(
                organization_id=job.organization_id,
                project_id=job.project_id,
                title=title[:200],
                **values,
            )
        count += 1
    return count


def _public_attrs(row: Any, fields: set[str]) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields if hasattr(row, field)}


async def _revision_rewrite_context(
    session: AsyncSession,
    *,
    organization_id: str,
    project: Project,
) -> dict[str, Any]:
    spec = await NovelSpecRepository(session).get_by(
        organization_id=organization_id,
        project_id=project.id,
    )
    characters = await CharacterRepository(session).list(
        organization_id=organization_id,
        project_id=project.id,
        limit=80,
        order_by=Character.created_at.asc(),
    )
    world_items = await WorldItemRepository(session).list(
        organization_id=organization_id,
        project_id=project.id,
        limit=120,
        order_by=WorldItem.created_at.asc(),
    )
    plot_threads = await PlotThreadRepository(session).list(
        organization_id=organization_id,
        project_id=project.id,
        limit=80,
        order_by=PlotThread.created_at.asc(),
    )
    chapters = await ChapterRepository(session).list(
        organization_id=organization_id,
        project_id=project.id,
        limit=200,
        order_by=Chapter.chapter_index.asc(),
    )
    return {
        "project": _public_attrs(
            project,
            {
                "id",
                "title",
                "genre",
                "target_word_count",
                "target_chapter_count",
                "style",
                "target_reader",
                "status",
            },
        ),
        "story_bible": None
        if not spec
        else _public_attrs(
            spec,
            {
                "id",
                "premise",
                "theme",
                "genre",
                "tone",
                "target_reader",
                "narrative_pov",
                "style_guide",
                "constraints",
                "continuity_rules",
            },
        ),
        "characters": [
            _public_attrs(
                row,
                {
                    "id",
                    "name",
                    "role",
                    "description",
                    "personality",
                    "motivation",
                    "secret",
                    "arc",
                    "relationships",
                    "current_state",
                },
            )
            for row in characters
        ],
        "world_items": [
            _public_attrs(
                row,
                {
                    "id",
                    "type",
                    "name",
                    "description",
                    "rules",
                    "related_characters",
                    "importance",
                    "is_hard_rule",
                },
            )
            for row in world_items
        ],
        "plot_threads": [
            _public_attrs(
                row,
                {
                    "id",
                    "title",
                    "thread_type",
                    "description",
                    "status",
                    "related_characters",
                },
            )
            for row in plot_threads
        ],
        "chapters": [
            _public_attrs(
                row,
                {
                    "id",
                    "chapter_index",
                    "title",
                    "summary",
                    "goal",
                    "conflict",
                    "ending_hook",
                    "status",
                },
            )
            for row in chapters
        ],
    }


def _story_bible_contract_schema() -> dict[str, Any]:
    return StoryBibleContract.model_json_schema()


def _revision_story_bible_counts(bible: StoryBibleContract) -> dict[str, int]:
    return {
        "characters": len(bible.main_characters or []),
        "locations": len(bible.locations or []),
        "factions": len(bible.factions or []),
        "world_rules": len(bible.world_rules or []),
        "plot_threads": len(bible.plot_threads or []),
    }


def _revision_context_counts(context: dict[str, Any]) -> dict[str, int]:
    return {
        "characters": len(context.get("characters") or []),
        "world_items": len(context.get("world_items") or []),
        "plot_threads": len(context.get("plot_threads") or []),
        "chapters": len(context.get("chapters") or []),
    }


@activity.defn(name="revision_rewrite_proposal")
async def revision_rewrite_proposal(job: dict[str, Any]) -> dict[str, Any]:
    """后台生成全项目重构提案，不直接改故事资产。"""
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        payload = job_row.input_payload or {}
        session_id = str(payload.get("revision_session_id") or "")
        revision_session = await RevisionSessionRepository(session).get(
            session_id,
            organization_id=job_row.organization_id,
        )
        if not revision_session or revision_session.project_id != job_row.project_id:
            raise NotFoundError("revision_session_not_found")

        context = await _revision_rewrite_context(
            session,
            organization_id=job_row.organization_id,
            project=project,
        )
        compact_context = {
            "project": context.get("project"),
            "story_bible": context.get("story_bible"),
            "characters": (context.get("characters") or [])[:12],
            "world_items": (context.get("world_items") or [])[:20],
            "plot_threads": (context.get("plot_threads") or [])[:20],
            "chapter_count": len(context.get("chapters") or []),
            "chapter_samples": (context.get("chapters") or [])[:8],
        }
        user_prompt = json.dumps(
            {
                "current_context": compact_context,
                "user_request": str(payload.get("message") or ""),
                "focus": {
                    "scope": payload.get("scope") or "story_bible",
                    "target_type": payload.get("target_type"),
                    "target_id": payload.get("target_id"),
                },
                "output_contract": "StoryBibleContract",
            },
            ensure_ascii=False,
        )
        model_timeout = max(
            get_settings().model_gateway_timeout_seconds,
            get_settings().model_gateway_long_timeout_seconds,
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            task_type="revision_rewrite_proposal",
            system_prompt=(
                "你是商业长篇小说总编辑。用户要求的是全项目级重构：必须基于当前项目"
                "全局上下文和用户修改要求，直接输出一份完整新版故事圣经。输出必须符合"
                "StoryBibleContract 本体，不要包裹 reply/story_bible 外层对象，不要输出建议清单。"
                "要把 Premise、Theme、Genre、Tone、POV、Style、人物、世界观、剧情线全部"
                "重写到可直接落库的结构。AI 只生成预览提案，不能直接改库。"
            ),
            user_prompt=user_prompt,
            schema=_story_bible_contract_schema(),
            prompt_key="revision/story_bible_rewrite",
            prompt_version="v2",
            temperature=0.7,
            metadata={
                "revision_session_id": session_id,
                "timeout_seconds": model_timeout,
            },
            timeout_seconds=model_timeout,
        )
        story_data = raw.get("story_bible") if isinstance(raw, dict) else None
        bible = StoryBibleContract.model_validate(story_data or raw)
        normalized = novel_planner_service._normalize_story_bible(
            bible,
            project,
            str(payload.get("message") or ""),
        )
        raw_summary = ""
        risk_notes: list[str] = []
        if isinstance(raw, dict):
            raw_summary = str(raw.get("reply") or raw.get("summary") or "").strip()
            if isinstance(raw.get("risk_notes"), list):
                risk_notes = [str(item) for item in raw["risk_notes"] if str(item).strip()]
        reply = raw_summary or "已生成一份完整新版故事圣经，可预览后应用。"
        patch = {
            "story_bible": normalized.model_dump(),
            "rewrite_plan": reply,
            "impact_counts": {
                "current": _revision_context_counts(context),
                "new": _revision_story_bible_counts(normalized),
            },
        }
        proposal = await RevisionProposalRepository(session).create(
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            session_id=session_id,
            target_type="story_bible_bundle",
            target_id=None,
            action="update",
            title="全项目重构：新版故事圣经快照",
            patch=patch,
            reason="基于当前全局上下文生成完整新版故事圣经；应用后可接入后续大纲、场景和正文重构。",
            impact=[
                "story_bible",
                "characters",
                "world_items",
                "plot_threads",
                "chapters",
                "scenes",
                "drafts",
            ],
            group_id=None,
            group_title="",
            is_primary=True,
            risk_notes=risk_notes
            or ["全项目重构会使旧大纲、场景和正文与新版设定不再一致。"],
            status="pending",
        )
        await RevisionMessageRepository(session).create(
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            session_id=session_id,
            role="assistant",
            content=reply,
        )
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {
            "revision_session_id": session_id,
            "proposal_ids": [proposal.id],
            "proposal_count": 1,
            "story_bible_counts": _revision_story_bible_counts(normalized),
        }


async def _settle_job_usage(session: AsyncSession, job: GenerationJob, amount: int) -> None:
    tenant = type("Tenant", (), {"organization_id": job.organization_id})()
    result = await session.execute(
        select(QuotaReservation).where(
            QuotaReservation.organization_id == job.organization_id,
            QuotaReservation.job_id == job.id,
        )
    )
    reservations = list(result.scalars().all())
    for reservation in reservations:
        await quota_service.commit_quota(
            session,
            tenant,
            reservation_id=reservation.id,
            actual_used=amount,
        )
    if amount > 0:
        await UsageEventRepository(session).create(
            organization_id=job.organization_id,
            user_id=job.user_id,
            project_id=job.project_id,
            job_id=job.id,
            event_type="generated_words",
            amount=amount,
            unit="words",
            event_metadata={"job_type": job.job_type},
        )
        job.consumed_quota = amount


async def _release_job_reservations(session: AsyncSession, job: GenerationJob) -> int:
    """释放 job 下仍处于 reserved 状态的额度预留。

    用于失败/取消路径，幂等：已 consumed/released 的预留会被 quota_service
    内部跳过，不会重复释放。返回实际释放的数量。
    """
    tenant = type("Tenant", (), {"organization_id": job.organization_id})()
    result = await session.execute(
        select(QuotaReservation).where(
            QuotaReservation.organization_id == job.organization_id,
            QuotaReservation.job_id == job.id,
            QuotaReservation.status == "reserved",
        )
    )
    reservations = list(result.scalars().all())
    for reservation in reservations:
        await quota_service.release_quota(
            session,
            tenant,
            reservation_id=reservation.id,
        )
    return len(reservations)


# job_type → 失败/取消时项目应回滚到的状态。
# 只有把 project.status 推到"过渡态"的 job 类型需要登记；不影响 project.status
# 的 job 类型（如 write_scene）不出现在此映射中。
_JOB_FAILURE_PROJECT_STATUS: dict[str, tuple[set[str], str]] = {
    # bible 生成失败：若项目仍卡在 bible_generating 过渡态，回退到 created
    "generate_bible": ({"bible_generating"}, "created"),
    # outline 生成失败：若项目仍卡在 outline_generating 过渡态，回退到 bible_ready
    "generate_outline": ({"outline_generating"}, "bible_ready"),
}


async def _has_project_rows(
    session: AsyncSession,
    job: GenerationJob,
    model: type,
) -> bool:
    stmt = (
        select(model.id)
        .where(
            model.organization_id == job.organization_id,
            model.project_id == job.project_id,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _infer_project_status_from_artifacts(
    session: AsyncSession,
    job: GenerationJob,
) -> str:
    if await _has_project_rows(session, job, DraftVersion):
        return "drafting"
    if await _has_project_rows(session, job, Scene):
        return "scenes_planned"
    if await _has_project_rows(session, job, Chapter):
        return "outlined"
    if await _has_project_rows(session, job, NovelSpec):
        return "bible_ready"
    return "created"


async def _revert_project_status_on_failure(
    session: AsyncSession, job: GenerationJob
) -> bool:
    """失败/取消时回滚 project.status，避免项目永久卡在过渡态。

    幂等：仅当 project.status 仍处于已登记的过渡态集合内才回滚；
    若项目已被其他流程推进或回滚，保持不动。返回是否实际回滚。
    """
    mapping = _JOB_FAILURE_PROJECT_STATUS.get(job.job_type)
    if not mapping or not job.project_id:
        return False
    transitional_states, target = mapping
    project = await ProjectRepository(session).get(
        job.project_id, organization_id=job.organization_id
    )
    if not project or project.status not in transitional_states:
        return False
    if job.job_type in {"generate_bible", "generate_outline"}:
        target = await _infer_project_status_from_artifacts(session, job)
    project.status = target
    return True


@activity.defn(name="mark_job_status")
async def mark_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
    output_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """更新 generation_jobs 的状态、时间戳，可选 error_message/output_payload。

    当 status 为 failed/cancelled 时，自动：
    1. 释放 job 名下仍处于 reserved 状态的额度预留（防止额度被幽灵预留）；
    2. 把 project.status 从 job 启动时设置的过渡态回滚（防止前端永久卡在
       "圣经生成中" 等中间态，影响重试入口）。
    两项操作都是幂等的。

    Sprint 12-A：每次状态变化向 ``project:{project_id}`` channel 推一条
    SSE 事件（``job.queued/running/succeeded/failed/cancelled``），让前端
    不再依赖 1.5s 轮询。publish 是 fire-and-forget，不阻塞 commit，
    Redis 不可达时优雅降级到 in-memory bus（同进程内仍生效）。
    """
    async with _activity_session() as session:
        repo = GenerationJobRepository(session)
        job = await repo.get(job_id)
        if not job:
            _logger.warning("mark_job_status: job_not_found", extra={"job_id": job_id})
            return {"updated": False}
        now = datetime.now(timezone.utc)
        job.status = status
        if status == "running" and job.started_at is None:
            job.started_at = now
        if status in {"succeeded", "failed", "cancelled"}:
            job.finished_at = now
        if error_message is not None:
            job.error_message = error_message
        if output_payload is not None:
            job.output_payload = output_payload
        released = 0
        project_reverted = False
        if status in {"failed", "cancelled"}:
            released = await _release_job_reservations(session, job)
            project_reverted = await _revert_project_status_on_failure(session, job)
        # 终态埋点：jobs_created_total{job_type, status} += 1
        # 只在 succeeded/failed/cancelled 终态计数，避免 queued→running 双重计数
        if status in {"succeeded", "failed", "cancelled"}:
            JOBS_CREATED.labels(job_type=job.job_type, status=status).inc()
        # SSE 事件：fire-and-forget，不阻塞 commit
        if job.project_id:
            publish_event_fire_and_forget(
                f"project:{job.project_id}",
                build_event(
                    f"job.{status}",
                    {
                        "job_id": job.id,
                        "job_type": job.job_type,
                        "status": status,
                        "project_id": job.project_id,
                        "scene_id": (job.input_payload or {}).get("scene_id"),
                        "chapter_id": (job.input_payload or {}).get("chapter_id"),
                        "error_message": error_message,
                    },
                ),
            )
        return {
            "updated": True,
            "status": status,
            "released_reservations": released,
            "project_status_reverted": project_reverted,
        }


@activity.defn(name="generate_book_spec")
async def generate_book_spec(job: dict[str, Any]) -> dict[str, Any]:
    """生成或补全 book spec，并落到 novel_specs。

    quota settle 行为：
    - 独立 generate_bible job：本 activity 负责把 reserved_quota 一次性 commit
    - full_novel job：父 GenerateFullNovelWorkflow 统一在 finalize 阶段按实际
      字数 settle；本 activity 跳过 settle 调用，避免提前 consume 父 reservation
      导致 write 阶段无法再 commit
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        payload = job_row.input_payload or {}
        # 子 activity 被 full_novel 复用：父 workflow 统一 settle，子步骤跳过
        skip_settle = job_row.job_type == "full_novel"
        spec_repo = NovelSpecRepository(session)
        existing = await spec_repo.get_by(
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
        )
        if (
            existing
            and existing.premise
            and existing.theme
            and not payload.get("force_regenerate_spec")
        ):
            project.status = "bible_ready"
            if not skip_settle:
                await _settle_job_usage(session, job_row, amount=0)
            return {"spec_id": existing.id, "reused": True, "premise": existing.premise}

        cleared_counts: dict[str, int] = {}
        if existing and payload.get("force_regenerate_spec"):
            cleared_counts = await _clear_story_bible_dependents(session, job_row)

        bible = await novel_planner_service.generate_story_bible(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            topic=str(payload.get("topic") or ""),
            creative_prefs=payload.get("creative_prefs") or {},
        )
        values = {
            "premise": bible.premise,
            "theme": bible.theme,
            "genre": bible.genre,
            "tone": bible.tone,
            "target_reader": bible.target_reader,
            "narrative_pov": bible.narrative_pov,
            "style_guide": bible.style_guide,
            "constraints": _contract_constraints(bible),
            "continuity_rules": list(bible.continuity_rules or []),
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            spec = existing
        else:
            spec = await spec_repo.create(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                **values,
            )
        project.genre = project.genre or bible.genre
        project.target_reader = project.target_reader or bible.target_reader
        project.style = project.style or bible.style_guide[:500]
        project.status = "bible_ready"
        character_count = await _sync_bible_characters(session, job_row, bible)
        world_item_count = await _sync_bible_world_items(session, job_row, bible)
        plot_thread_count = await _sync_bible_plot_threads(session, job_row, bible)
        if not skip_settle:
            await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {
            "spec_id": spec.id,
            "reused": False,
            "premise": spec.premise,
            "character_count": character_count,
            "world_item_count": world_item_count,
            "plot_thread_count": plot_thread_count,
            "cleared_counts": cleared_counts,
        }


@activity.defn(name="generate_chapter_outline")
async def generate_chapter_outline(job: dict[str, Any]) -> dict[str, Any]:
    """按 book spec 生成章节规划，并落到 chapters。

    独立 workflow 调用时负责结算 quota；full_novel pipeline 中也调用本 activity，
    但 generate_book_spec 已经在 happy path 一次性结算了整 job 的 quota，再次
    settle 由 quota_service.commit_quota 的 `status != 'reserved'` 守卫保证幂等。

    GenerateFullNovelWorkflow（Sprint 12-B）路径下：父 workflow 在 finalize
    阶段按实际写出字数 settle，子 activity（spec / outline）跳过 settle，
    避免预先 consume 让 finalize 无 reservation 可写。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        payload = job_row.input_payload or {}
        skip_settle = job_row.job_type == "full_novel"
        chapter_repo = ChapterRepository(session)
        existing = list(
            await chapter_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        requested = payload.get("target_chapters") or project.target_chapter_count or 6
        target_total_chapters = max(1, min(int(requested), MAX_OUTLINE_CHAPTERS))
        existing_count = len(existing)
        batch_target_chapters = min(
            target_total_chapters,
            existing_count + OUTLINE_CHAPTER_BATCH_SIZE,
        )
        if existing and not payload.get("force_regenerate_outline"):
            if existing_count >= target_total_chapters:
                project.status = "outlined"
                if not skip_settle:
                    await _settle_job_usage(session, job_row, amount=0)
                return {
                    "chapter_count": existing_count,
                    "target_chapter_count": target_total_chapters,
                    "remaining_chapter_count": 0,
                    "reused": True,
                }

        # force_regenerate=True：先显式清掉旧大纲/场景/正文/审稿问题，再写新章节。
        # Postgres 初始化表没有 ON DELETE CASCADE，不能依赖 FK 自动清理。
        if existing and payload.get("force_regenerate_outline"):
            await _clear_outline_dependents(session, job_row)
            existing = []
            existing_count = 0
            batch_target_chapters = min(
                target_total_chapters,
                OUTLINE_CHAPTER_BATCH_SIZE,
            )

        contract = await novel_planner_service.plan_chapters(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            bible=spec,
            target_chapters=target_total_chapters,
            start_chapter_index=existing_count + 1,
            end_chapter_index=batch_target_chapters,
            character_roster=await _character_roster_for_prompt(session, job_row),
            existing_outline=_chapter_outline_context(existing),
        )
        existing_indices = {chapter.chapter_index for chapter in existing}
        # Sprint 16-E1：当 LLM 没给 target_words 时，按项目级目标字数反推默认值。
        # project.target_word_count / target_chapter_count 都是 ProjectCreate 必给字段，
        # 默认 300_000 / 48 → 6250 字/章；可在 outline 阶段被 LLM 覆盖。
        default_target = max(
            500,
            (project.target_word_count or 0) // max(1, project.target_chapter_count or 1),
        )
        created = 0
        for item in contract.chapters:
            if item.chapter_index in existing_indices:
                continue
            chapter_target = item.target_words if item.target_words > 0 else default_target
            # Sprint 17-B 节奏：归一 emotion_intensity 到 1-5，pacing_type 留空表示未指定
            emo = max(1, min(int(item.emotion_intensity or 3), 5))
            await chapter_repo.create(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                volume_id=None,
                chapter_index=item.chapter_index,
                title=item.title,
                summary=item.summary,
                goal=item.goal,
                conflict=item.conflict,
                ending_hook=item.ending_hook,
                status="planned",
                target_words=chapter_target,
                scene_beats=list(item.scene_beats or []),
                pacing_type=(item.pacing_type or "").strip().lower(),
                emotion_intensity=emo,
            )
            created += 1
        total_chapters = len(existing) + created
        if target_total_chapters > (project.target_chapter_count or 0):
            project.target_chapter_count = target_total_chapters
        else:
            project.target_chapter_count = project.target_chapter_count or total_chapters
        project.status = "outlined"
        if not skip_settle:
            await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {
            "chapter_count": total_chapters,
            "created_chapter_count": created,
            "target_chapter_count": target_total_chapters,
            "batch_target_chapter_count": batch_target_chapters,
            "remaining_chapter_count": max(0, target_total_chapters - total_chapters),
            "reused": False,
            "appended": bool(existing),
        }


def _chapter_outline_context(chapters: list[Chapter], *, limit: int = 20) -> str:
    """压缩前文大纲，供分批续写章节时承接剧情。"""
    if not chapters:
        return ""
    ordered = sorted(chapters, key=lambda item: item.chapter_index)
    selected = ordered[-limit:]
    if ordered[0] not in selected:
        selected = [ordered[0], *selected]
    parts: list[str] = []
    for chapter in selected:
        summary = chapter.summary or chapter.goal or chapter.ending_hook or ""
        parts.append(f"第{chapter.chapter_index}章《{chapter.title}》：{summary[:180]}")
    return "\n".join(parts)


async def _plan_and_persist_scenes_for_chapter(
    session: AsyncSession,
    *,
    job: GenerationJob,
    project: Project,
    spec: NovelSpec,
    chapter: Chapter,
    scenes_per_chapter: int | None,
    expected_words: int,
) -> list[Scene]:
    """单章 scene cards 规划 + 落库的共享流程。

    被 generate_scene_cards（项目级循环）和 generate_chapter_scene_cards
    （单章模式）两个 activity 复用。返回写入的 Scene ORM 对象列表，调用方
    可以基于它做 memory 写入等后处理。

    Sprint 16-E2：当 chapter.scene_beats 非空时，scene 数取 beats 长度（覆盖
    调用方传入的 scenes_per_chapter）；同时按 chapter.target_words / scene 数
    精准给每场 target_words，避免一锅端把字数算炸。
    """
    effective_scene_count = scenes_per_chapter
    beats = list(chapter.scene_beats or [])
    if beats:
        effective_scene_count = max(2, min(len(beats), 6))
    effective_expected_words = expected_words
    if chapter.target_words and chapter.target_words > 0 and effective_scene_count:
        effective_expected_words = max(
            400, chapter.target_words // max(1, effective_scene_count)
        )
    previous_chapter_context = await context_builder.build_previous_chapter_context(
        session,
        organization_id=job.organization_id,
        project_id=job.project_id,
        chapter=chapter,
    )
    contract = await novel_planner_service.plan_scenes(
        session,
        organization_id=job.organization_id,
        project_id=job.project_id,
        job_id=job.id,
        project=project,
        bible=spec,
        chapter=chapter,
        scenes_per_chapter=effective_scene_count,
        expected_words=effective_expected_words,
        character_roster=await _character_roster_for_prompt(session, job),
        previous_chapter_context=previous_chapter_context,
    )
    scene_limit = effective_scene_count or 8
    scene_repo = SceneRepository(session)
    created: list[Scene] = []
    for item in contract.scenes[:scene_limit]:
        row = await scene_repo.create(
            organization_id=job.organization_id,
            project_id=job.project_id,
            chapter_id=chapter.id,
            scene_index=item.scene_index,
            title=item.title,
            time_marker=item.time_marker,
            location=item.location,
            characters=item.characters,
            scene_purpose=item.scene_purpose,
            entry_state=item.entry_state,
            exit_state=item.exit_state,
            goal=item.goal,
            conflict=item.conflict,
            must_include=item.must_include,
            must_avoid=item.must_avoid,
            emotion_start=item.emotion_start,
            emotion_end=item.emotion_end,
            reveal=item.reveal,
            hook=item.hook,
            status="planned",
        )
        created.append(row)
    return created


@activity.defn(name="generate_scene_cards")
async def generate_scene_cards(job: dict[str, Any]) -> dict[str, Any]:
    """项目级：按所有章节规划拆 scene cards，并落到 scenes。

    用于 full_novel pipeline；单章场景生成请使用 generate_chapter_scene_cards。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        payload = job_row.input_payload or {}
        scene_repo = SceneRepository(session)
        existing = list(
            await scene_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Scene.scene_index.asc(),
            )
        )
        if existing and not payload.get("force_regenerate_scenes"):
            project.status = "scenes_planned"
            return {"scene_count": len(existing), "reused": True}
        # force=True 时先全删旧 scenes，再批量重生成
        if existing and payload.get("force_regenerate_scenes"):
            await _delete_project_rows(session, job_row, ContinuityIssue)
            await _delete_project_rows(session, job_row, DraftVersion)
            await _delete_project_rows(session, job_row, MemoryEntry, source_type="scene")
            await _delete_project_rows(session, job_row, Scene)

        chapters = list(
            await ChapterRepository(session).list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        raw_scenes_per_chapter = payload.get("scenes_per_chapter")
        scenes_per_chapter = (
            max(2, min(int(raw_scenes_per_chapter), 8))
            if raw_scenes_per_chapter is not None
            else None
        )
        estimate_words = _payload_int(payload, "estimate_words", 20000)
        expected_scene_count = scenes_per_chapter or 3
        expected_words = max(600, estimate_words // max(1, len(chapters) * expected_scene_count))
        created = 0
        for chapter in chapters:
            new_scenes = await _plan_and_persist_scenes_for_chapter(
                session,
                job=job_row,
                project=project,
                spec=spec,
                chapter=chapter,
                scenes_per_chapter=scenes_per_chapter,
                expected_words=expected_words,
            )
            created += len(new_scenes)
        project.status = "scenes_planned"
        return {"scene_count": created, "reused": False}


@activity.defn(name="generate_chapter_scene_cards")
async def generate_chapter_scene_cards(job: dict[str, Any]) -> dict[str, Any]:
    """章节级：仅为 input_payload.chapter_id 指定的章节生成 scene cards。

    不改变 project.status —— 单章生成属于"局部更新"，不应把整个项目推到
    scenes_planned；项目级 status 只在 full_novel pipeline 内部推进。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        payload = job_row.input_payload or {}

        chapter_id = payload.get("chapter_id")
        if not chapter_id:
            raise NotFoundError("chapter_id_required")
        chapter = await ChapterRepository(session).get(
            chapter_id, organization_id=job_row.organization_id
        )
        if not chapter or chapter.project_id != project.id:
            raise NotFoundError("chapter_not_found")

        scene_repo = SceneRepository(session)
        existing = list(
            await scene_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                order_by=Scene.scene_index.asc(),
            )
        )
        force = bool(payload.get("force_regenerate_scenes"))
        if existing and not force:
            await _settle_job_usage(session, job_row, amount=0)
            return {
                "scene_count": len(existing),
                "chapter_id": chapter.id,
                "reused": True,
            }
        # force=True 时先删除旧场景，避免 scene_index 重复追加
        if existing and force:
            old_scene_ids = [scene.id for scene in existing]
            await _delete_project_rows(session, job_row, ContinuityIssue, chapter_id=chapter.id)
            await _delete_project_rows(session, job_row, ContinuityIssue, scene_id=old_scene_ids)
            await _delete_project_rows(session, job_row, DraftVersion, chapter_id=chapter.id)
            await _delete_project_rows(session, job_row, DraftVersion, scene_id=old_scene_ids)
            await _delete_project_rows(
                session,
                job_row,
                MemoryEntry,
                source_type="scene",
                source_id=old_scene_ids,
            )
            await _delete_project_rows(session, job_row, Scene, chapter_id=chapter.id)

        raw_scenes_per_chapter = payload.get("scenes_per_chapter")
        scenes_per_chapter = (
            max(2, min(int(raw_scenes_per_chapter), 8))
            if raw_scenes_per_chapter is not None
            else None
        )
        expected_words = max(600, _payload_int(payload, "expected_words", 1500))
        new_scenes = await _plan_and_persist_scenes_for_chapter(
            session,
            job=job_row,
            project=project,
            spec=spec,
            chapter=chapter,
            scenes_per_chapter=scenes_per_chapter,
            expected_words=expected_words,
        )
        # 每个新 scene 写一条 memory_entry 摘要，给 ContextBuilder.recent_summary 喂料
        for scene in new_scenes:
            await context_builder.record_scene_memory(
                session,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene=scene,
                chapter=chapter,
            )
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {
            "scene_count": len(new_scenes),
            "chapter_id": chapter.id,
            "reused": False,
        }


@activity.defn(name="write_scene_drafts")
async def write_scene_drafts(job: dict[str, Any]) -> dict[str, Any]:
    """逐场景写正文草稿，并落到 draft_versions。"""
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        payload = job_row.input_payload or {}
        if payload.get("write_drafts") is False:
            project.status = "scenes_planned"
            return {
                "draft_count": 0,
                "created_draft_count": 0,
                "reused_draft_count": 0,
                "word_count": 0,
                "skipped": True,
            }
        scene_repo = SceneRepository(session)
        draft_repo = DraftVersionRepository(session)
        chapters = list(
            await ChapterRepository(session).list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        chapter_by_id = {chapter.id: chapter for chapter in chapters}
        scenes = list(
            await scene_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
            )
        )
        scenes.sort(
            key=lambda scene: (
                chapter_by_id[scene.chapter_id].chapter_index,
                scene.scene_index,
            )
        )
        existing_drafts = list(
            await draft_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
            )
        )
        draft_by_scene: dict[str, DraftVersion] = {
            draft.scene_id: draft
            for draft in existing_drafts
            if draft.scene_id and draft.version_type == "draft"
        }
        estimate_words = _payload_int(payload, "estimate_words", 20000)
        force = bool(payload.get("force_regenerate_drafts"))
        created = 0
        reused = 0
        total_words = sum(draft.word_count for draft in draft_by_scene.values())
        # Sprint 16-E2：按 chapter 分组算 target_words / scene，让每场都贴合
        # chapter.target_words 预算；旧 chapter（target_words=0）回落到旧的
        # estimate_words 平摊逻辑。
        scenes_by_chapter: dict[str, list[Scene]] = {}
        for scene in scenes:
            scenes_by_chapter.setdefault(scene.chapter_id, []).append(scene)
        chapter_target_words: dict[str, int] = {}
        for chapter_id, chapter_scenes in scenes_by_chapter.items():
            chapter = chapter_by_id[chapter_id]
            scene_count = max(1, len(chapter_scenes))
            if chapter.target_words and chapter.target_words > 0:
                chapter_target_words[chapter_id] = max(
                    400, chapter.target_words // scene_count
                )
            else:
                chapter_target_words[chapter_id] = max(
                    600, estimate_words // max(1, len(scenes))
                )
        previous_excerpt = ""
        for scene in scenes:
            chapter = chapter_by_id[scene.chapter_id]
            if scene.id in draft_by_scene and not force:
                previous_excerpt = draft_by_scene[scene.id].content[-1500:]
                reused += 1
                continue
            target_words = chapter_target_words[chapter.id]
            draft = await writer_service.write_scene_draft(
                session,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                job_id=job_row.id,
                project=project,
                spec=spec,
                chapter=chapter,
                scene=scene,
                previous_scene_excerpt=previous_excerpt,
                target_words=target_words,
            )
            word_count = len(draft.content)
            saved = await draft_repo.create(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                version_type="draft",
                content=draft.content,
                content_format="markdown",
                word_count=word_count,
                status="draft",
                parent_version_id=None,
                created_by=job_row.user_id,
            )
            scene.status = "drafted"
            _spawn_moderation_check(
                draft.content,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene_id=scene.id,
                source="write_scene_drafts",
            )
            await _run_ledger_check(session, 
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene_id=scene.id,
                draft_content=draft.content,
                source="write_scene_drafts",
            )
            await memory_service.update_character_states_from_scene(
                session,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                job_id=job_row.id,
                chapter=chapter,
                scene=scene,
                draft=saved,
            )
            # Sprint 16-E4：章内同步等待三链推演（与 single scene workflow 行为对齐）
            if get_settings().inchapter_extract_enabled:
                await _run_chapter_in_extracts(
                    session,
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    job_id=job_row.id,
                    chapter=chapter,
                    scene=scene,
                    draft=saved,
                    created_by=job_row.user_id,
                )
            previous_excerpt = draft.content[-1500:]
            total_words += word_count
            created += 1
        project.current_word_count = total_words
        project.completed_chapter_count = len(chapters) if scenes else 0
        project.status = "drafting"
        # Sprint 16-E5：本次 batch 内每个有新 draft 落地的 chapter 触发一次
        # summarize_chapter（fire-and-forget）。同章重复触发是安全的（summarizer
        # 会追加新 L2 不覆盖），但用 set 去重避免无谓 LLM 调用。
        touched_chapter_ids = {
            scene.chapter_id
            for scene in scenes
            if scene.id not in draft_by_scene or force
        }
        for chapter_id in touched_chapter_ids:
            _spawn_chapter_summarize(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter_id,
                source="write_scene_drafts",
            )
        # Sprint 17-A 防漂移：每 10 章触发一次 L3 弧线摘要
        for chapter_id in touched_chapter_ids:
            chap = chapter_by_id.get(chapter_id)
            if chap and chap.chapter_index and chap.chapter_index % 10 == 0:
                _spawn_arc_summarize(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    start_chapter_index=chap.chapter_index - 9,
                    end_chapter_index=chap.chapter_index,
                    source="write_scene_drafts",
                )
        # Sprint 17-A 防漂移：每 50 章触发角色 milestone snapshot
        max_touched_index = max(
            (
                chapter_by_id[cid].chapter_index
                for cid in touched_chapter_ids
                if cid in chapter_by_id
            ),
            default=0,
        )
        if max_touched_index and max_touched_index % 50 == 0:
            _spawn_character_milestones(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_index=max_touched_index,
                source="write_scene_drafts",
            )
        # Sprint 17-A 防漂移：每 20 章触发长程审计
        for chapter_id in touched_chapter_ids:
            chap = chapter_by_id.get(chapter_id)
            if chap and chap.chapter_index and chap.chapter_index % 20 == 0:
                _spawn_long_range_audit(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_id=chap.id,
                    source="write_scene_drafts",
                )
        # Sprint 17-A 防漂移：每 100 章触发风格漂移检测
        for chapter_id in touched_chapter_ids:
            chap = chapter_by_id.get(chapter_id)
            if chap and chap.chapter_index and chap.chapter_index % 100 == 0:
                _spawn_style_drift_check(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_id=chap.id,
                    chapter_index=chap.chapter_index,
                    source="write_scene_drafts",
                )
        # Sprint 17-C 方案 3：章末润色 pass（默认关闭）
        if get_settings().chapter_polish_enabled:
            for chapter_id in touched_chapter_ids:
                _spawn_chapter_polish(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_id=chapter_id,
                    user_id=job_row.user_id,
                    source="write_scene_drafts",
                )
        return {
            "draft_count": created + reused,
            "created_draft_count": created,
            "reused_draft_count": reused,
            "word_count": total_words,
        }


@activity.defn(name="run_scene_writing")
async def run_scene_writing(job: dict[str, Any]) -> dict[str, Any]:
    """单 scene 写作 activity。

    Sprint 4 升级：
    - scene 状态机：planned/drafted → writing → drafted，让前端轮询期间能
      看到中间态（本地短链路很快，真实 provider 时持续到模型返回）。
    - DraftVersion 父链：把上一个 draft 作为 parent_version_id，构成版本链，
      未来在 UI 上可显示历史变迁。
    - 上一场景结尾片段：从同章前一个 scene 的最新 draft 取最后 800 字作为
      previous_excerpt 传给 writer，提高跨场景连贯性。
    - 独立 quota 结算：与 generate_chapter_scene_cards 对齐。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        payload = job_row.input_payload or {}
        scene_id = payload.get("scene_id")
        if not scene_id:
            raise NotFoundError("scene_id_required")
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        scene = await SceneRepository(session).get(
            scene_id, organization_id=job_row.organization_id
        )
        if not scene or scene.project_id != project.id:
            raise NotFoundError("scene_not_found")
        chapter = await ChapterRepository(session).get(
            scene.chapter_id,
            organization_id=job_row.organization_id,
        )
        if not chapter:
            raise NotFoundError("chapter_not_found")

        # 状态机：先置 "writing"，让轮询前端能看到中间态
        scene.status = "writing"
        await session.flush()

        target_words = _payload_int(payload, "target_words", 1200)
        previous_excerpt = await _previous_scene_excerpt(session, scene)
        draft = await writer_service.write_scene_draft(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            previous_scene_excerpt=previous_excerpt,
            target_words=target_words,
        )
        word_count = len(draft.content)

        # 版本链：把本 scene 的最新 draft 作为父版本
        parent_version_id = await _latest_draft_id(session, scene)
        saved = await DraftVersionRepository(session).create(
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            version_type="draft",
            content=draft.content,
            content_format="markdown",
            word_count=word_count,
            status="draft",
            parent_version_id=parent_version_id,
            created_by=job_row.user_id,
        )
        scene.status = "drafted"
        _spawn_moderation_check(
            draft.content,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            scene_id=scene.id,
            source="run_scene_writing",
        )
        await _run_ledger_check(session, 
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            scene_id=scene.id,
            draft_content=draft.content,
            source="run_scene_writing",
        )
        memory_result = await memory_service.update_character_states_from_scene(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            chapter=chapter,
            scene=scene,
            draft=saved,
        )

        # 与 generate_chapter_scene_cards 对称：单 scene 写作自身结算 quota
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)

        # ContextBuilder Inspector：把本次喂给模型的上下文摘要存到 output_payload。
        # 这里二次 build 一份相同上下文（纯 db 查询，~10ms），代价是避免侵入
        # writer 的返回类型与现有调用方。前端从 jobs API 直接读 output_payload。
        ctx_inspector = await context_builder.build_for_scene_writing(
            session,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            previous_excerpt=previous_excerpt,
        )
        context_summary = [
            {
                "label": seg.label,
                "trusted": seg.trusted,
                "token_budget": seg.token_budget,
                "estimated_tokens": seg.estimated_tokens,
                "truncated": seg.truncated,
                # 限定预览长度，避免 output_payload 撑大
                "preview": seg.content[:240],
            }
            for seg in ctx_inspector.segments
            if seg.content
        ]

        result = {
            "scene_id": scene.id,
            "draft_id": saved.id,
            "word_count": word_count,
            "parent_version_id": parent_version_id,
            "context_summary": context_summary,
            "context_total_tokens": ctx_inspector.total_tokens,
            "memory": memory_result,
        }
        job_row.output_payload = result
        return result


async def _previous_scene_excerpt(session: AsyncSession, scene: Scene) -> str:
    """取前一场景的最新 draft 末尾片段，跨章自动回溯到上一章末场。

    - 同章内：直接取 scene_index - 1 的最新 draft 末尾 1500 字。
    - 新章首场（scene_index == 1）：回溯到上一章 chapter_index - 1 的最后
      一个 scene，取其最新 draft 末尾 1500 字，让 writer 能承接前章结尾。
    - 找不到上一章 / 上一场或没有 draft 时返回空字符串。失败不阻断主流程。
    """
    excerpt_chars = 1500
    scene_repo = SceneRepository(session)
    draft_repo = DraftVersionRepository(session)

    prev_scene: Scene | None = None
    if scene.scene_index > 1:
        siblings = list(
            await scene_repo.list(
                organization_id=scene.organization_id,
                project_id=scene.project_id,
                chapter_id=scene.chapter_id,
            )
        )
        prev_scene = next(
            (s for s in siblings if s.scene_index == scene.scene_index - 1), None
        )
    else:
        chap_repo = ChapterRepository(session)
        cur_chapter = await chap_repo.get(
            scene.chapter_id, organization_id=scene.organization_id
        )
        if cur_chapter and cur_chapter.chapter_index > 1:
            chapters = list(
                await chap_repo.list(
                    organization_id=scene.organization_id,
                    project_id=scene.project_id,
                )
            )
            prev_chapter = next(
                (c for c in chapters if c.chapter_index == cur_chapter.chapter_index - 1),
                None,
            )
            if prev_chapter:
                prev_scenes = list(
                    await scene_repo.list(
                        organization_id=scene.organization_id,
                        project_id=scene.project_id,
                        chapter_id=prev_chapter.id,
                    )
                )
                if prev_scenes:
                    prev_scene = max(prev_scenes, key=lambda s: s.scene_index)

    if not prev_scene:
        return ""
    drafts = list(
        await draft_repo.list(
            organization_id=scene.organization_id,
            project_id=scene.project_id,
            scene_id=prev_scene.id,
            status="draft",
        )
    )
    if not drafts:
        return ""
    # base list 默认按 created_at desc 排序，第 0 个就是最新
    return drafts[0].content[-excerpt_chars:]


async def _latest_draft_id(session: AsyncSession, scene: Scene) -> str | None:
    """取该 scene 的最新可用版本 id，用作审稿/重写/新版本父节点。"""
    repo = DraftVersionRepository(session)
    drafts = list(
        await repo.list(
            organization_id=scene.organization_id,
            project_id=scene.project_id,
            scene_id=scene.id,
            status="draft",
            limit=1,
        )
    )
    return drafts[0].id if drafts else None


@activity.defn(name="run_full_novel_pipeline")
async def run_full_novel_pipeline(job: dict[str, Any]) -> dict[str, Any]:
    """兼容入口：按 GOAT 风格顺序执行完整分层流水线。

    用于 TEMPORAL_ENABLED=false 的 local fire-and-forget 路径（见
    workflow_starter._execute_local）。Temporal worker 路径走
    GenerateFullNovelWorkflow 的批/child workflow 编排，不调本函数。

    quota settle：本函数是 full_novel job 的"独立结算者"——spec/outline 子
    activity 在 full_novel job_type 下都已被改成 skip_settle，所以这里必须
    在结束前显式调一次 _settle_job_usage 把父 reservation 提交，否则父 job
    会一直停在 reserved 状态。
    """
    spec = await generate_book_spec(job)
    chapters = await generate_chapter_outline(job)
    scenes = await generate_scene_cards(job)
    drafts = await write_scene_drafts(job)
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
    return {
        "book_spec": spec,
        "chapters": chapters,
        "scenes": scenes,
        "drafts": drafts,
    }


# ----------------------------------------------------------------------------
# Full novel orchestrator activities
# ----------------------------------------------------------------------------
# GenerateFullNovelWorkflow 用这一组 activity 把 full_novel 拆成可按章节批次
# 推进的链路，每章一个 child workflow，支持 continue_as_new 切下一批。
# 与历史 run_full_novel_pipeline（一次性顺序跑全程）相比：
# - 父 workflow 的 history 始终保持在数百条 event 之内（一批 K 章）
# - 单章子 workflow 失败不阻断其他章，由父 workflow try/except 隔离
# - quota 预估 = target_chapters × avg_words_per_chapter，settle 由父 workflow
#   在最后一批结束时一次性按"实际写出的字数"提交，避免重复 settle
#
# 这些 activity 都使用**显式参数**而非 input_payload，便于 child workflow 复用
# 父 full_novel job_id 而无需污染父 job 的 input_payload 字段。


@activity.defn(name="prepare_full_novel")
async def prepare_full_novel(job: dict[str, Any]) -> dict[str, Any]:
    """父 workflow 启动时调用：

    1. 把父 job.status 切到 running
    2. 确保 NovelSpec 存在（首次启动会复用 generate_book_spec activity 内部
       逻辑，并按 input_payload 字段决定是否 force）
    3. 确保 chapters 已落库；若没有则调 generate_chapter_outline
    4. 返回 chapter_id 升序列表 + 每章预估字数，供 orchestrator 分批

    幂等：continue_as_new 之后再次进入也会重跑本步骤；book_spec/chapter
    activities 自身已带 reuse 分支，不会重复扣额度或重新生成。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        # 父 full_novel job 在 prepare 阶段就推到 running；后续 continue_as_new
        # 再次进入时 mark_job_status 是幂等的（已经 running 时不动 started_at）。
        if job_row.status != "running":
            job_row.status = "running"
            if job_row.started_at is None:
                job_row.started_at = datetime.now(timezone.utc)
            await session.flush()

    # 复用 generate_book_spec / generate_chapter_outline 各自的 reuse 路径，
    # 让 full_novel 入口与单独入口共享逻辑。两个 activity 内部各自管理
    # 自己的 quota settle（reused 分支不扣额度）。
    await generate_book_spec(job)
    await generate_chapter_outline(job)

    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        chapters = list(
            await ChapterRepository(session).list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        payload = job_row.input_payload or {}
        target_chapters = _payload_int(payload, "target_chapters", len(chapters)) or len(chapters)
        scenes_per_chapter = max(1, min(_payload_int(payload, "scenes_per_chapter", 3), 8))
        estimate_words = max(1, _payload_int(payload, "estimate_words", 20000))
        # 估算每章每场景字数：让 writer 收敛到目标总字数附近，又不至于把
        # 单场景压到极短（最低 600）。
        total_scenes = max(1, target_chapters * scenes_per_chapter)
        target_words_per_scene = max(600, estimate_words // total_scenes)
        return {
            "chapter_ids": [c.id for c in chapters],
            "chapter_indices": [c.chapter_index for c in chapters],
            "scenes_per_chapter": scenes_per_chapter,
            "target_words_per_scene": target_words_per_scene,
            "estimate_words": estimate_words,
            "target_chapters": target_chapters,
        }


@activity.defn(name="plan_chapter_scenes_for_full_novel")
async def plan_chapter_scenes_for_full_novel(
    job_id: str,
    chapter_id: str,
    scenes_per_chapter: int,
    expected_words: int,
) -> dict[str, Any]:
    """父 full_novel orchestrator 用：为指定 chapter 生成 scene cards。

    与 generate_chapter_scene_cards 的区别：
    - 不读 input_payload.chapter_id（避免覆写父 job 的 payload）
    - 不在内部 settle quota（父 workflow 统一在最后 settle）
    - 已有 scenes 时直接 reuse，不重生成
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job_id)
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        chapter = await ChapterRepository(session).get(
            chapter_id, organization_id=job_row.organization_id
        )
        if not chapter or chapter.project_id != project.id:
            raise NotFoundError("chapter_not_found")
        scenes_per_chapter = max(1, min(int(scenes_per_chapter or 3), 8))
        expected_words = max(600, int(expected_words or 1200))

        scene_repo = SceneRepository(session)
        existing = list(
            await scene_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                order_by=Scene.scene_index.asc(),
            )
        )
        if existing:
            return {
                "chapter_id": chapter.id,
                "scene_ids": [scene.id for scene in existing],
                "reused": True,
            }
        new_scenes = await _plan_and_persist_scenes_for_chapter(
            session,
            job=job_row,
            project=project,
            spec=spec,
            chapter=chapter,
            scenes_per_chapter=scenes_per_chapter,
            expected_words=expected_words,
        )
        return {
            "chapter_id": chapter.id,
            "scene_ids": [scene.id for scene in new_scenes],
            "reused": False,
        }


@activity.defn(name="write_chapter_scenes_for_full_novel")
async def write_chapter_scenes_for_full_novel(
    job_id: str,
    chapter_id: str,
    target_words_per_scene: int,
) -> dict[str, Any]:
    """父 full_novel orchestrator 用：串行写一章内所有 scenes 的 draft。

    - 已有 draft 的 scene 直接跳过（reused）
    - 写每个 scene 前做 quota preflight：父 job 的 (reserved - consumed) <
      target_words 时跳过，并标 skipped
    - 不在内部 settle quota；父 workflow 在 finalize_full_novel 中统一 settle
    - 写完更新 character 状态 + 写 memory entry（沿用 run_scene_writing 的链路）
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job_id)
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        chapter = await ChapterRepository(session).get(
            chapter_id, organization_id=job_row.organization_id
        )
        if not chapter or chapter.project_id != project.id:
            raise NotFoundError("chapter_not_found")

        scene_repo = SceneRepository(session)
        scenes = list(
            await scene_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                order_by=Scene.scene_index.asc(),
            )
        )
        if not scenes:
            return {
                "chapter_id": chapter.id,
                "scenes_drafted": 0,
                "scenes_reused": 0,
                "scenes_skipped": 0,
                "words": 0,
                "scene_results": [],
            }

        draft_repo = DraftVersionRepository(session)
        words_written = 0
        drafted = 0
        reused = 0
        skipped = 0
        scene_results: list[dict[str, Any]] = []
        # quota preflight 基线：父 job 一开始 reserved 全部预算；这里用
        # reserved_quota - consumed_quota 作为"剩余可花"，每写一个 scene
        # 都更新 consumed_quota（暂态，最终在 finalize_full_novel 内 settle）。
        budget_left = max(0, (job_row.reserved_quota or 0) - (job_row.consumed_quota or 0))
        target_words = max(600, int(target_words_per_scene or 1200))

        for scene in scenes:
            existing_drafts = list(
                await draft_repo.list(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    scene_id=scene.id,
                    version_type="draft",
                )
            )
            if existing_drafts:
                reused += 1
                scene_results.append({
                    "scene_id": scene.id,
                    "status": "reused",
                    "words": existing_drafts[0].word_count or 0,
                })
                continue
            if budget_left < target_words:
                skipped += 1
                scene_results.append({
                    "scene_id": scene.id,
                    "status": "skipped_quota",
                    "words": 0,
                })
                continue

            scene.status = "writing"
            await session.flush()
            previous_excerpt = await _previous_scene_excerpt(session, scene)
            draft = await writer_service.write_scene_draft(
                session,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                job_id=job_row.id,
                project=project,
                spec=spec,
                chapter=chapter,
                scene=scene,
                previous_scene_excerpt=previous_excerpt,
                target_words=target_words,
            )
            word_count = len(draft.content)
            saved = await draft_repo.create(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                version_type="draft",
                content=draft.content,
                content_format="markdown",
                word_count=word_count,
                status="draft",
                parent_version_id=None,
                created_by=job_row.user_id,
            )
            scene.status = "drafted"
            _spawn_moderation_check(
                draft.content,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene_id=scene.id,
                source="write_scene_drafts",
            )
            await _run_ledger_check(session, 
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene_id=scene.id,
                draft_content=draft.content,
                source="write_scene_drafts",
            )
            await memory_service.update_character_states_from_scene(
                session,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                job_id=job_row.id,
                chapter=chapter,
                scene=scene,
                draft=saved,
            )
            # Sprint 16-E4：章内同步等待三链推演（与 single scene workflow 对齐）
            if get_settings().inchapter_extract_enabled:
                await _run_chapter_in_extracts(
                    session,
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    job_id=job_row.id,
                    chapter=chapter,
                    scene=scene,
                    draft=saved,
                    created_by=job_row.user_id,
                )
            drafted += 1
            words_written += word_count
            budget_left = max(0, budget_left - word_count)
            scene_results.append({
                "scene_id": scene.id,
                "status": "drafted",
                "words": word_count,
                "draft_id": saved.id,
            })

        # 更新 chapter 状态：若本章所有 scenes 都已 drafted/reused → 标 drafted
        if drafted + reused == len(scenes) and skipped == 0:
            chapter.status = "drafted"
            # Sprint 16-E5：章末 fire-and-forget summarize_chapter，产 L2 摘要
            _spawn_chapter_summarize(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                source="write_chapter_scenes_for_full_novel",
            )
            # Sprint 17-A 防漂移：每 10 章触发一次 L3 弧线摘要
            if chapter.chapter_index and chapter.chapter_index % 10 == 0:
                _spawn_arc_summarize(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    start_chapter_index=chapter.chapter_index - 9,
                    end_chapter_index=chapter.chapter_index,
                    source="write_chapter_scenes_for_full_novel",
                )
            # Sprint 17-A 防漂移：每 50 章触发角色 milestone snapshot
            if chapter.chapter_index and chapter.chapter_index % 50 == 0:
                _spawn_character_milestones(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_index=chapter.chapter_index,
                    source="write_chapter_scenes_for_full_novel",
                )
            # Sprint 17-A 防漂移：每 20 章触发长程审计
            if chapter.chapter_index and chapter.chapter_index % 20 == 0:
                _spawn_long_range_audit(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_id=chapter.id,
                    source="write_chapter_scenes_for_full_novel",
                )
            # Sprint 17-A 防漂移：每 100 章触发风格漂移检测
            if chapter.chapter_index and chapter.chapter_index % 100 == 0:
                _spawn_style_drift_check(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_id=chapter.id,
                    chapter_index=chapter.chapter_index,
                    source="write_chapter_scenes_for_full_novel",
                )
            # Sprint 17-C 方案 3：章末润色 pass（默认关闭）
            if get_settings().chapter_polish_enabled:
                _spawn_chapter_polish(
                    organization_id=job_row.organization_id,
                    project_id=job_row.project_id,
                    chapter_id=chapter.id,
                    user_id=job_row.user_id,
                    source="write_chapter_scenes_for_full_novel",
                )
        # 父 job 的 consumed_quota 临时累加，给后续 chapter 预算判断用；
        # 真正落 usage_event 由 finalize_full_novel 处理。
        job_row.consumed_quota = (job_row.consumed_quota or 0) + words_written
        return {
            "chapter_id": chapter.id,
            "scenes_drafted": drafted,
            "scenes_reused": reused,
            "scenes_skipped": skipped,
            "words": words_written,
            "scene_results": scene_results,
        }


@activity.defn(name="finalize_full_novel")
async def finalize_full_novel(
    job_id: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """父 full_novel workflow 在所有批次完成后调用：

    - 把汇总 metric 写入 output_payload
    - 调 _settle_job_usage 按"实际产出字数"结算 quota（不写出 = 不扣）
    - 推进 project.status / 更新 current_word_count
    - mark_job_status 单独由 workflow 在外层调用，保持与其他 workflow 的
      日志/重试一致；本 activity 只负责结算与汇总
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job_id)
        project = await _load_project(session, job_row)
        words = int(metrics.get("scenes_words") or 0)
        # 真实消耗 = max(本次写出的字数, 0)；若全部章节都因 quota 不足被
        # skipped，amount=0 → settle 走 release 路径。
        await _settle_job_usage(session, job_row, amount=words)
        project.current_word_count = max(project.current_word_count or 0, words)
        project.completed_chapter_count = int(metrics.get("chapters_drafted") or 0)
        if int(metrics.get("chapters_drafted") or 0) > 0:
            project.status = "drafting"
        summary = {
            "chapters_total": int(metrics.get("chapters_total") or 0),
            "chapters_drafted": int(metrics.get("chapters_drafted") or 0),
            "chapters_failed": int(metrics.get("chapters_failed") or 0),
            "chapters_skipped": int(metrics.get("chapters_skipped") or 0),
            "scenes_drafted": int(metrics.get("scenes_drafted") or 0),
            "scenes_reused": int(metrics.get("scenes_reused") or 0),
            "scenes_failed": int(metrics.get("scenes_failed") or 0),
            "scenes_skipped": int(metrics.get("scenes_skipped") or 0),
            "scenes_words": words,
            "failed_chapter_ids": list(metrics.get("failed_chapter_ids") or []),
        }
        # output_payload 由 mark_job_status(succeeded, output=...) 写入；
        # 这里同时也回填一份，避免依赖外层 status 调用的执行顺序。
        job_row.output_payload = summary
        return summary


@activity.defn(name="audit_scene")
async def audit_scene(job: dict[str, Any]) -> dict[str, Any]:
    """对单个 scene 的最新 draft 审稿，把发现的问题写入 continuity_issues。

    input_payload 字段：
      - scene_id (必填)

    返回 result：
      - scene_id / draft_id 用于联动
      - issue_count: 新写入的问题数（0 表示无问题）
      - issues: 摘要数组，UI 可以即时展示
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        payload = job_row.input_payload or {}
        scene_id = payload.get("scene_id")
        if not scene_id:
            raise NotFoundError("scene_id_required")
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        scene = await SceneRepository(session).get(
            scene_id, organization_id=job_row.organization_id
        )
        if not scene or scene.project_id != project.id:
            raise NotFoundError("scene_not_found")
        chapter = await ChapterRepository(session).get(
            scene.chapter_id, organization_id=job_row.organization_id
        )
        if not chapter:
            raise NotFoundError("chapter_not_found")

        # 加载最新 draft 作为待审稿文本
        latest_draft_id = await _latest_draft_id(session, scene)
        if not latest_draft_id:
            raise NotFoundError("draft_not_found")
        draft_repo = DraftVersionRepository(session)
        latest_draft = await draft_repo.get(
            latest_draft_id, organization_id=job_row.organization_id
        )
        if not latest_draft:
            raise NotFoundError("draft_not_found")

        contract = await auditor_service.audit_scene_draft(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            draft_content=latest_draft.content,
        )

        issue_repo = ContinuityIssueRepository(session)
        existing_open_issues = list(
            await issue_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene_id=scene.id,
                status="open",
            )
        )
        for issue in existing_open_issues:
            issue.status = "superseded"

        created_issues: list[dict[str, Any]] = []
        for item in contract.issues:
            row = await issue_repo.create(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                issue_type=item.issue_type,
                severity=item.severity,
                description=item.description,
                suggested_fix=item.suggested_fix,
                status="open",
            )
            created_issues.append(
                {
                    "id": row.id,
                    "issue_type": row.issue_type,
                    "severity": row.severity,
                    "description": row.description,
                }
            )

        # 不动 scene.status —— 审稿是"附加分析"，scene 仍处于 drafted 状态
        # 等用户决定 rewrite 时才推到 "writing" 再到 "drafted"。
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)

        return {
            "scene_id": scene.id,
            "draft_id": latest_draft.id,
            "issue_count": len(created_issues),
            "issues": created_issues,
        }


@activity.defn(name="polish_chapter")
async def polish_chapter(job: dict[str, Any]) -> dict[str, Any]:
    """Sprint 17-C 方案 3：整章 N 场 draft 一次性润色，落 version_type='polish' draft。

    input_payload 字段：
      - chapter_id (必填)
      - force (可选 bool，默认 False)：True 时绕过 dedupe

    返回：
      - chapter_id / draft_id / word_count / status (skipped|created|dedup)
    任何失败 swallow + warn，绝不破坏主 job。
    """
    from app.services.polisher import polish_chapter as _do  # noqa: PLC0415

    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        payload = job_row.input_payload or {}
        chapter_id = payload.get("chapter_id")
        if not chapter_id:
            raise NotFoundError("chapter_id_required")
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        chapter = await ChapterRepository(session).get(
            chapter_id, organization_id=job_row.organization_id
        )
        if not chapter or chapter.project_id != project.id:
            raise NotFoundError("chapter_not_found")
        draft = await _do(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            spec=spec,
            chapter=chapter,
            created_by=job_row.user_id,
            force=bool(payload.get("force")),
        )
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        if draft is None:
            return {
                "chapter_id": chapter.id,
                "draft_id": None,
                "status": "skipped",
                "reason": "no_drafts_or_quality_or_dedup",
            }
        return {
            "chapter_id": chapter.id,
            "draft_id": draft.id,
            "word_count": draft.word_count,
            "status": "created",
        }


@activity.defn(name="rewrite_scene")
async def rewrite_scene(job: dict[str, Any]) -> dict[str, Any]:
    """基于当前 scene 的 open issues 重写 draft，并把那些 issues 标 fixed。

    input_payload 字段：
      - scene_id (必填)
      - target_words (可选，默认 1200)

    activity 自动捞取本 scene 的所有 open issues，全部送给 rewriter；
    Sprint 5-A 不提供 "只修复某几条" 的细粒度。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        payload = job_row.input_payload or {}
        scene_id = payload.get("scene_id")
        if not scene_id:
            raise NotFoundError("scene_id_required")
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        scene = await SceneRepository(session).get(
            scene_id, organization_id=job_row.organization_id
        )
        if not scene or scene.project_id != project.id:
            raise NotFoundError("scene_not_found")
        chapter = await ChapterRepository(session).get(
            scene.chapter_id, organization_id=job_row.organization_id
        )
        if not chapter:
            raise NotFoundError("chapter_not_found")

        latest_draft_id = await _latest_draft_id(session, scene)
        if not latest_draft_id:
            raise NotFoundError("draft_not_found")
        draft_repo = DraftVersionRepository(session)
        latest_draft = await draft_repo.get(
            latest_draft_id, organization_id=job_row.organization_id
        )
        if not latest_draft:
            raise NotFoundError("draft_not_found")

        # 取当前 scene 所有 open issues。空列表也能 rewrite（仅做风格打磨）。
        issue_repo = ContinuityIssueRepository(session)
        issues = list(
            await issue_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                scene_id=scene.id,
                status="open",
            )
        )

        scene.status = "writing"
        await session.flush()

        target_words = _payload_int(payload, "target_words", 1200)
        new_draft = await rewriter_service.rewrite_scene_draft(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            current_content=latest_draft.content,
            issues=issues,
            target_words=target_words,
        )
        word_count = len(new_draft.content)
        saved = await draft_repo.create(
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            version_type="rewrite",
            content=new_draft.content,
            content_format="markdown",
            word_count=word_count,
            status="draft",
            parent_version_id=latest_draft.id,
            created_by=job_row.user_id,
        )
        scene.status = "drafted"
        _spawn_moderation_check(
            new_draft.content,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            scene_id=scene.id,
            source="rewrite_scene",
        )
        await _run_ledger_check(session, 
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            scene_id=scene.id,
            draft_content=new_draft.content,
            source="rewrite_scene",
        )

        # 把本次涉及的 issues 标 fixed（不删除，保留可审计的修复历史）
        for issue in issues:
            issue.status = "fixed"

        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)

        return {
            "scene_id": scene.id,
            "draft_id": saved.id,
            "parent_version_id": latest_draft.id,
            "word_count": word_count,
            "fixed_issue_count": len(issues),
        }


@activity.defn(name="extract_character_state_from_scene")
async def extract_character_state_from_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """从场景正文反推角色状态变化，落 character_revisions（status='pending'）。

    Sprint 10 Phase B：write_scene / rewrite_scene 主 activity 完成后由
    workflow fire-and-forget 调用；本 activity 内部捕获所有异常，绝不抛出，
    避免推演失败影响主流程已成功的 scene 写作。

    payload 字段：
      - organization_id (必填)
      - project_id      (必填)
      - scene_id        (必填)
      - draft_id        (必填，用于取最新正文)
      - created_by      (必填，用作 revision.created_by)
    """
    from app.services.character_tracker.extract import (
        extract_state_changes_from_scene,
    )

    try:
        async with _activity_session() as session:
            draft_repo = DraftVersionRepository(session)
            draft = await draft_repo.get(
                payload["draft_id"], organization_id=payload["organization_id"]
            )
            if not draft:
                return {"changes_written": 0, "reason": "draft_not_found"}
            written = await extract_state_changes_from_scene(
                session,
                organization_id=payload["organization_id"],
                project_id=payload["project_id"],
                scene_id=payload["scene_id"],
                scene_content=draft.content or "",
                created_by=payload["created_by"],
            )
            return {"changes_written": written}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("extract_character_state activity_failed: %s", exc)
        return {"changes_written": 0, "error": str(exc)}


@activity.defn(name="refine_character_arcs_from_outline")
async def refine_character_arcs_from_outline(payload: dict[str, Any]) -> dict[str, Any]:
    """Outline 完成后基于 chapters 三幕结构精细化角色 motivation/arc/secret。

    Sprint 11 Phase E：GenerateOutlineWorkflow 主 activity 完成后 fire-and-forget
    调用本 activity；失败仅打日志，不影响 outline 已 succeeded 的状态。

    payload 字段：
      - organization_id (必填)
      - project_id      (必填)
      - created_by      (必填，用作 revision.created_by)
    """
    from app.services.character_tracker.refine_arcs import (
        extract_character_arcs_from_outline,
    )

    try:
        async with _activity_session() as session:
            written = await extract_character_arcs_from_outline(
                session,
                organization_id=payload["organization_id"],
                project_id=payload["project_id"],
                created_by=payload["created_by"],
            )
            return {"refinements_written": written}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("refine_character_arcs activity_failed: %s", exc)
        return {"refinements_written": 0, "error": str(exc)}


ALL_ACTIVITIES = [
    mark_job_status,
    generate_book_spec,
    generate_chapter_outline,
    generate_scene_cards,
    generate_chapter_scene_cards,
    write_scene_drafts,
    run_scene_writing,
    audit_scene,
    rewrite_scene,
    run_full_novel_pipeline,
    revision_rewrite_proposal,
    extract_character_state_from_scene,
    refine_character_arcs_from_outline,
    # Sprint 12-B full-novel orchestrator activities
    prepare_full_novel,
    plan_chapter_scenes_for_full_novel,
    write_chapter_scenes_for_full_novel,
    finalize_full_novel,
]


# ---------------------------------------------------------------------------
# Sprint 12-C: world / plot 演进推演 activities
# ---------------------------------------------------------------------------
# fire-and-forget：write_scene / rewrite_scene 完成后由 workflow 异步触发，
# 失败 swallow + warn，绝不阻塞主链路。
@activity.defn(name="extract_world_changes_from_scene")
async def extract_world_changes_from_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """对单 scene 反推 world_item 字段变化，写 pending revision。

    payload 必填字段：scene_id；可选：job_id（用于 model_call 关联）。
    返回 {"pending_count": N, "considered_count": M}。任何异常都被吞掉，
    workflow 不会因此失败。
    """
    from app.services.world_tracker.extract import (  # noqa: PLC0415
        extract_world_changes_from_scene as _do,
    )

    scene_id = payload.get("scene_id")
    job_id = payload.get("job_id")
    if not scene_id:
        return {"pending_count": 0, "skipped": True, "reason": "scene_id_missing"}

    try:
        async with _activity_session() as session:
            scene = await SceneRepository(session).get(scene_id)
            if not scene:
                return {"pending_count": 0, "skipped": True, "reason": "scene_not_found"}
            chapter = await ChapterRepository(session).get(
                scene.chapter_id, organization_id=scene.organization_id
            )
            if not chapter:
                return {"pending_count": 0, "skipped": True, "reason": "chapter_not_found"}
            drafts = list(
                await DraftVersionRepository(session).list(
                    organization_id=scene.organization_id,
                    project_id=scene.project_id,
                    scene_id=scene.id,
                    limit=1,
                )
            )
            if not drafts:
                return {"pending_count": 0, "skipped": True, "reason": "draft_missing"}
            return await _do(
                session,
                organization_id=scene.organization_id,
                project_id=scene.project_id,
                job_id=job_id,
                chapter=chapter,
                scene=scene,
                draft=drafts[0],
            )
    except Exception:  # noqa: BLE001
        _logger.warning("extract_world_changes_activity_failed", exc_info=True)
        return {"pending_count": 0, "error": "swallowed"}


@activity.defn(name="extract_plot_thread_changes_from_scene")
async def extract_plot_thread_changes_from_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """对单 scene 反推 plot_thread 字段变化，写 pending revision。"""
    from app.services.plot_thread_tracker.extract import (  # noqa: PLC0415
        extract_plot_thread_changes_from_scene as _do,
    )

    scene_id = payload.get("scene_id")
    job_id = payload.get("job_id")
    if not scene_id:
        return {"pending_count": 0, "skipped": True, "reason": "scene_id_missing"}

    try:
        async with _activity_session() as session:
            scene = await SceneRepository(session).get(scene_id)
            if not scene:
                return {"pending_count": 0, "skipped": True, "reason": "scene_not_found"}
            chapter = await ChapterRepository(session).get(
                scene.chapter_id, organization_id=scene.organization_id
            )
            if not chapter:
                return {"pending_count": 0, "skipped": True, "reason": "chapter_not_found"}
            drafts = list(
                await DraftVersionRepository(session).list(
                    organization_id=scene.organization_id,
                    project_id=scene.project_id,
                    scene_id=scene.id,
                    limit=1,
                )
            )
            if not drafts:
                return {"pending_count": 0, "skipped": True, "reason": "draft_missing"}
            return await _do(
                session,
                organization_id=scene.organization_id,
                project_id=scene.project_id,
                job_id=job_id,
                chapter=chapter,
                scene=scene,
                draft=drafts[0],
            )
    except Exception:  # noqa: BLE001
        _logger.warning("extract_plot_thread_changes_activity_failed", exc_info=True)
        return {"pending_count": 0, "error": "swallowed"}


@activity.defn(name="extract_temporal_state_from_scene")
async def extract_temporal_state_from_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """Sprint 17-B 全局时间线：反推当前场的 in_story_day_offset /
    time_of_day / duration_minutes 并直接写回 scenes 表。

    payload 字段：
      - scene_id (必填)
      - job_id   (可选)
    失败 swallow + warn，不阻断主流程。
    """
    from app.services.temporal_tracker.extract import (  # noqa: PLC0415
        extract_temporal_state_from_scene as _do,
    )

    scene_id = payload.get("scene_id")
    job_id = payload.get("job_id")
    if not scene_id:
        return {"updated": False, "skipped": "scene_id_missing"}

    try:
        async with _activity_session() as session:
            scene = await SceneRepository(session).get(scene_id)
            if not scene:
                return {"updated": False, "skipped": "scene_not_found"}
            chapter = await ChapterRepository(session).get(
                scene.chapter_id, organization_id=scene.organization_id
            )
            if not chapter:
                return {"updated": False, "skipped": "chapter_not_found"}
            drafts = list(
                await DraftVersionRepository(session).list(
                    organization_id=scene.organization_id,
                    project_id=scene.project_id,
                    scene_id=scene.id,
                    limit=1,
                )
            )
            if not drafts:
                return {"updated": False, "skipped": "draft_missing"}
            return await _do(
                session,
                organization_id=scene.organization_id,
                project_id=scene.project_id,
                job_id=job_id,
                chapter=chapter,
                scene=scene,
                draft=drafts[0],
            )
    except Exception:  # noqa: BLE001
        _logger.warning("extract_temporal_state_activity_failed", exc_info=True)
        return {"updated": False, "error": "swallowed"}


ALL_ACTIVITIES.extend(
    [
        extract_world_changes_from_scene,
        extract_plot_thread_changes_from_scene,
        extract_temporal_state_from_scene,
    ]
)
