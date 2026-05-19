"""Temporal Activities。

工作流只编排步骤；所有模型调用、数据库写入都放在 activity 内。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from app.core.database import AsyncSessionLocal
from app.core.exceptions import NotFoundError
from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.generation_job import GenerationJob
from app.models.quota import QuotaReservation
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.repositories import (
    ChapterRepository,
    CharacterRepository,
    DraftVersionRepository,
    GenerationJobRepository,
    NovelSpecRepository,
    PlotThreadRepository,
    ProjectRepository,
    UsageEventRepository,
    WorldItemRepository,
    SceneRepository,
)
from app.services.novel_planner.service import novel_planner_service
from app.services.quota.service import quota_service
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
    - world_rules → world_items 表
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
            "motivation": seed.motivation,
            "arc": seed.arc,
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
    for index, rule in enumerate(bible.world_rules or [], start=1):
        text = str(rule).strip()
        if not text:
            continue
        name = text[:80] or f"世界规则 {index}"
        existing = await repo.get_by(
            organization_id=job.organization_id,
            project_id=job.project_id,
            name=name,
        )
        values = {
            "type": "rule",
            "description": text,
            "rules": {"source": "story_bible"},
            "related_characters": [],
            "importance": "high",
            "is_hard_rule": True,
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
        return {
            "updated": True,
            "status": status,
            "released_reservations": released,
            "project_status_reverted": project_reverted,
        }


@activity.defn(name="generate_book_spec")
async def generate_book_spec(job: dict[str, Any]) -> dict[str, Any]:
    """生成或补全 book spec，并落到 novel_specs。"""
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        payload = job_row.input_payload or {}
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
            await _settle_job_usage(session, job_row, amount=0)
            return {"spec_id": existing.id, "reused": True, "premise": existing.premise}

        bible = await novel_planner_service.generate_story_bible(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            topic=str(payload.get("topic") or ""),
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
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {
            "spec_id": spec.id,
            "reused": False,
            "premise": spec.premise,
            "character_count": character_count,
            "world_item_count": world_item_count,
            "plot_thread_count": plot_thread_count,
        }


@activity.defn(name="generate_chapter_outline")
async def generate_chapter_outline(job: dict[str, Any]) -> dict[str, Any]:
    """按 book spec 生成章节规划，并落到 chapters。

    独立 workflow 调用时负责结算 quota；full_novel pipeline 中也调用本 activity，
    但 generate_book_spec 已经在 happy path 一次性结算了整 job 的 quota，再次
    settle 由 quota_service.commit_quota 的 `status != 'reserved'` 守卫保证幂等。
    """
    async with _activity_session() as session:
        job_row = await _load_job(session, job["id"])
        project = await _load_project(session, job_row)
        spec = await _load_spec(session, job_row)
        payload = job_row.input_payload or {}
        chapter_repo = ChapterRepository(session)
        existing = list(
            await chapter_repo.list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        if existing and not payload.get("force_regenerate_outline"):
            project.status = "outlined"
            await _settle_job_usage(session, job_row, amount=0)
            return {"chapter_count": len(existing), "reused": True}

        requested = payload.get("target_chapters") or project.target_chapter_count or 6
        target_chapters = max(1, min(int(requested), 12))
        contract = await novel_planner_service.plan_chapters(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            project=project,
            bible=spec,
            target_chapters=target_chapters,
        )
        created = 0
        for item in contract.chapters:
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
            )
            created += 1
        project.target_chapter_count = project.target_chapter_count or created
        project.status = "outlined"
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {"chapter_count": created, "reused": False}


async def _plan_and_persist_scenes_for_chapter(
    session: AsyncSession,
    *,
    job: GenerationJob,
    project: Project,
    spec: NovelSpec,
    chapter: Chapter,
    scenes_per_chapter: int,
    expected_words: int,
) -> int:
    """单章 scene cards 规划 + 落库的共享流程。

    被 generate_scene_cards（项目级循环）和 generate_chapter_scene_cards
    （单章模式）两个 activity 复用，避免重复代码。返回写入的 scene 数量。
    """
    contract = await novel_planner_service.plan_scenes(
        session,
        organization_id=job.organization_id,
        project_id=job.project_id,
        job_id=job.id,
        project=project,
        bible=spec,
        chapter=chapter,
        scenes_per_chapter=scenes_per_chapter,
        expected_words=expected_words,
    )
    scene_repo = SceneRepository(session)
    created = 0
    for item in contract.scenes[:scenes_per_chapter]:
        await scene_repo.create(
            organization_id=job.organization_id,
            project_id=job.project_id,
            chapter_id=chapter.id,
            scene_index=item.scene_index,
            title=item.title,
            time_marker=item.time_marker,
            location=item.location,
            characters=item.characters,
            goal=item.goal,
            conflict=item.conflict,
            emotion_start=item.emotion_start,
            emotion_end=item.emotion_end,
            reveal=item.reveal,
            hook=item.hook,
            status="planned",
        )
        created += 1
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

        chapters = list(
            await ChapterRepository(session).list(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        scenes_per_chapter = max(1, min(_payload_int(payload, "scenes_per_chapter", 3), 8))
        estimate_words = _payload_int(payload, "estimate_words", 20000)
        expected_words = max(600, estimate_words // max(1, len(chapters) * scenes_per_chapter))
        created = 0
        for chapter in chapters:
            created += await _plan_and_persist_scenes_for_chapter(
                session,
                job=job_row,
                project=project,
                spec=spec,
                chapter=chapter,
                scenes_per_chapter=scenes_per_chapter,
                expected_words=expected_words,
            )
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

        scenes_per_chapter = max(1, min(_payload_int(payload, "scenes_per_chapter", 3), 8))
        expected_words = max(600, _payload_int(payload, "expected_words", 1500))
        created = await _plan_and_persist_scenes_for_chapter(
            session,
            job=job_row,
            project=project,
            spec=spec,
            chapter=chapter,
            scenes_per_chapter=scenes_per_chapter,
            expected_words=expected_words,
        )
        await _settle_job_usage(session, job_row, amount=job_row.reserved_quota)
        return {
            "scene_count": created,
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
        target_words = max(600, estimate_words // max(1, len(scenes)))
        force = bool(payload.get("force_regenerate_drafts"))
        created = 0
        reused = 0
        total_words = sum(draft.word_count for draft in draft_by_scene.values())
        previous_excerpt = ""
        for scene in scenes:
            chapter = chapter_by_id[scene.chapter_id]
            if scene.id in draft_by_scene and not force:
                previous_excerpt = draft_by_scene[scene.id].content[-800:]
                reused += 1
                continue
            draft = await writer_service.write_scene_draft(
                session,
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                job_id=job_row.id,
                spec=spec,
                chapter=chapter,
                scene=scene,
                previous_scene_excerpt=previous_excerpt,
                target_words=target_words,
            )
            word_count = draft.word_count or len(draft.content)
            await draft_repo.create(
                organization_id=job_row.organization_id,
                project_id=job_row.project_id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                version_type="draft",
                content=draft.content,
                word_count=word_count,
                status="draft",
                parent_version_id=None,
                created_by=job_row.user_id,
            )
            scene.status = "drafted"
            previous_excerpt = draft.content[-800:]
            total_words += word_count
            created += 1
        project.current_word_count = total_words
        project.completed_chapter_count = len(chapters) if scenes else 0
        project.status = "drafting"
        return {
            "draft_count": created + reused,
            "created_draft_count": created,
            "reused_draft_count": reused,
            "word_count": total_words,
        }


@activity.defn(name="run_scene_writing")
async def run_scene_writing(job: dict[str, Any]) -> dict[str, Any]:
    """单 scene 写作 activity。"""
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
        target_words = _payload_int(payload, "target_words", 1200)
        draft = await writer_service.write_scene_draft(
            session,
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            job_id=job_row.id,
            spec=spec,
            chapter=chapter,
            scene=scene,
            target_words=target_words,
        )
        word_count = draft.word_count or len(draft.content)
        saved = await DraftVersionRepository(session).create(
            organization_id=job_row.organization_id,
            project_id=job_row.project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            version_type="draft",
            content=draft.content,
            word_count=word_count,
            status="draft",
            parent_version_id=None,
            created_by=job_row.user_id,
        )
        scene.status = "drafted"
        result = {"scene_id": scene.id, "draft_id": saved.id, "word_count": word_count}
        job_row.output_payload = result
        return result


@activity.defn(name="run_full_novel_pipeline")
async def run_full_novel_pipeline(job: dict[str, Any]) -> dict[str, Any]:
    """兼容入口：按 GOAT 风格顺序执行完整分层流水线。"""
    spec = await generate_book_spec(job)
    chapters = await generate_chapter_outline(job)
    scenes = await generate_scene_cards(job)
    drafts = await write_scene_drafts(job)
    return {
        "book_spec": spec,
        "chapters": chapters,
        "scenes": scenes,
        "drafts": drafts,
    }


ALL_ACTIVITIES = [
    mark_job_status,
    generate_book_spec,
    generate_chapter_outline,
    generate_scene_cards,
    generate_chapter_scene_cards,
    write_scene_drafts,
    run_scene_writing,
    run_full_novel_pipeline,
]
