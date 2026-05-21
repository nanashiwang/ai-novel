"""分层摘要记忆 Summarizer（Sprint 14-C2）。

把 memory_entries 中的低层（L1 scene、L2 chapter、L3 volume）摘要按弧线
聚合到更高层，写回同一张表（level/arc_window 字段）。

设计要点：
- LLM 主路径：调 model_gateway.generate_text + prompts/memory/summarize_arc.md。
- 失败回落：拼接 + 截断的确定性 fallback，不阻断主流程。
- 写入：MemoryRepository.create()，statement 提交由调用方控制（活动里通常
  会随同 _activity_session 一起 commit）。
- 兼容 SQLite：仅依赖 ORM 字段，没有 pgvector / embedding 硬依赖。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.memory import MemoryEntry
from app.repositories import (
    ChapterRepository,
    MemoryRepository,
    VolumeRepository,
)
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_KEY = "memory/summarize_arc"
_PROMPT_VERSION = "v1"
_MAX_FALLBACK_CHARS = 1200
_logger = logging.getLogger(__name__)


class HierarchicalSummarizer:
    """构造 L2/L3/L4 摘要并写回 memory_entries。"""

    async def summarize_chapter(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
        job_id: str | None = None,
    ) -> MemoryEntry | None:
        """把单章下所有 L1 (scene) 摘要聚合成 1 条 L2。

        - 当章节下没有任何 L1 摘要时直接返回 None，不写空记录。
        - 同章重复调用会追加新的 L2 条目（不覆盖历史），方便审计；
          ContextBuilder 召回时按 created_at desc 取最近一条。
        """
        chapter = await ChapterRepository(session).get(
            chapter_id, organization_id=organization_id
        )
        if not chapter or chapter.project_id != project_id:
            return None

        sources = await self._collect_chapter_sources(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
        )
        if not sources:
            return None

        arc_window = f"ch{chapter.chapter_index}"
        title = f"第 {chapter.chapter_index} 章弧线摘要"
        content = await self._summarize(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            level="L2",
            arc_window=arc_window,
            sources=sources,
            context_hint=(
                f"章节《{chapter.title}》（第 {chapter.chapter_index} 章）"
                f" 目标：{chapter.goal or '—'}；冲突：{chapter.conflict or '—'}。"
            ),
        )
        return await self._persist(
            session,
            organization_id=organization_id,
            project_id=project_id,
            level="L2",
            arc_window=arc_window,
            source_type="chapter",
            source_id=chapter.id,
            memory_type="arc_summary",
            title=title,
            content=content,
        )

    async def summarize_volume(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        volume_id: str,
        job_id: str | None = None,
    ) -> MemoryEntry | None:
        """聚合 volume 下所有 L2 → 1 条 L3。"""
        volume = await VolumeRepository(session).get(
            volume_id, organization_id=organization_id
        )
        if not volume or volume.project_id != project_id:
            return None

        chapters = list(
            await ChapterRepository(session).list(
                organization_id=organization_id,
                project_id=project_id,
                volume_id=volume_id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        if not chapters:
            return None
        chapter_ids = [c.id for c in chapters]
        sources = await self._collect_level_sources(
            session,
            organization_id=organization_id,
            project_id=project_id,
            level="L2",
            source_type="chapter",
            source_ids=chapter_ids,
        )
        if not sources:
            return None

        first_idx = chapters[0].chapter_index
        last_idx = chapters[-1].chapter_index
        arc_window = (
            f"vol{volume.volume_index}:ch{first_idx}-ch{last_idx}"
            if first_idx != last_idx
            else f"vol{volume.volume_index}:ch{first_idx}"
        )
        title = f"第 {volume.volume_index} 卷弧线摘要"
        content = await self._summarize(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            level="L3",
            arc_window=arc_window,
            sources=sources,
            context_hint=(
                f"卷《{volume.title}》（第 {volume.volume_index} 卷）"
                f" 目标：{volume.goal or '—'}。"
            ),
        )
        return await self._persist(
            session,
            organization_id=organization_id,
            project_id=project_id,
            level="L3",
            arc_window=arc_window,
            source_type="volume",
            source_id=volume.id,
            memory_type="arc_summary",
            title=title,
            content=content,
        )

    async def summarize_book(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str | None = None,
    ) -> MemoryEntry | None:
        """聚合所有 L3（卷摘要） → 1 条 L4。若没有 L3，则回落到 L2 全集。"""
        # 先尝试基于 L3 聚合
        stmt = (
            select(MemoryEntry)
            .where(
                MemoryEntry.organization_id == organization_id,
                MemoryEntry.project_id == project_id,
                MemoryEntry.level == "L3",
            )
            .order_by(MemoryEntry.created_at.desc())
        )
        l3_rows = list((await session.execute(stmt)).scalars().all())
        # 同一 source_id（同一卷）只保留最新一条
        l3_by_source = self._dedupe_by_source(l3_rows)
        if l3_by_source:
            sources = [(row.title, row.content) for row in l3_by_source]
        else:
            sources = await self._collect_level_sources(
                session,
                organization_id=organization_id,
                project_id=project_id,
                level="L2",
            )
        if not sources:
            return None

        arc_window = "book"
        title = "整书弧线摘要"
        content = await self._summarize(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            level="L4",
            arc_window=arc_window,
            sources=sources,
            context_hint="本书整体走向：请抽取主线、关键转折与人物长期变化。",
        )
        return await self._persist(
            session,
            organization_id=organization_id,
            project_id=project_id,
            level="L4",
            arc_window=arc_window,
            source_type="book",
            source_id=project_id,
            memory_type="arc_summary",
            title=title,
            content=content,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _collect_chapter_sources(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
    ) -> list[tuple[str, str]]:
        """取该章节所有 source_type='scene' 的 L1 摘要。

        通过 scenes.chapter_id 关联 memory_entries.source_id（scene.id）。
        """
        from app.models.scene import Scene  # 局部导入避免循环引用

        scene_stmt = (
            select(Scene.id)
            .where(
                Scene.organization_id == organization_id,
                Scene.project_id == project_id,
                Scene.chapter_id == chapter.id,
            )
            .order_by(Scene.scene_index.asc())
        )
        scene_ids = [row for row in (await session.execute(scene_stmt)).scalars().all()]
        if not scene_ids:
            return []

        mem_stmt = (
            select(MemoryEntry)
            .where(
                MemoryEntry.organization_id == organization_id,
                MemoryEntry.project_id == project_id,
                MemoryEntry.source_type == "scene",
                MemoryEntry.source_id.in_(scene_ids),
                MemoryEntry.level == "L1",
            )
            .order_by(MemoryEntry.created_at.asc())
        )
        rows = list((await session.execute(mem_stmt)).scalars().all())
        # 同一 scene 多次写入时只保留最新
        latest = self._dedupe_by_source(rows, prefer_latest=True)
        return [(row.title or row.memory_type or "scene", row.content) for row in latest]

    async def _collect_level_sources(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        level: str,
        source_type: str | None = None,
        source_ids: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        stmt = (
            select(MemoryEntry)
            .where(
                MemoryEntry.organization_id == organization_id,
                MemoryEntry.project_id == project_id,
                MemoryEntry.level == level,
            )
            .order_by(MemoryEntry.created_at.asc())
        )
        if source_type:
            stmt = stmt.where(MemoryEntry.source_type == source_type)
        if source_ids is not None:
            if not source_ids:
                return []
            stmt = stmt.where(MemoryEntry.source_id.in_(source_ids))
        rows = list((await session.execute(stmt)).scalars().all())
        latest = self._dedupe_by_source(rows, prefer_latest=True)
        return [(row.title or row.memory_type or "summary", row.content) for row in latest]

    @staticmethod
    def _dedupe_by_source(
        rows: list[MemoryEntry], *, prefer_latest: bool = True
    ) -> list[MemoryEntry]:
        """同一 source_id 多条时只留 1 条；保持顺序稳定。"""
        seen: dict[str, MemoryEntry] = {}
        for row in rows:
            key = row.source_id
            existing = seen.get(key)
            if existing is None:
                seen[key] = row
                continue
            if prefer_latest and row.created_at and existing.created_at:
                if row.created_at > existing.created_at:
                    seen[key] = row
        # 保持插入顺序（按 created_at asc 输入）
        return list(seen.values())

    async def _summarize(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str | None,
        level: str,
        arc_window: str,
        sources: list[tuple[str, str]],
        context_hint: str,
    ) -> str:
        """主路径走 LLM；任何异常都回落到 fallback。"""
        try:
            prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
            joined = "\n\n".join(
                f"### {title}\n{content}".strip() for title, content in sources
            )
            user_prompt = (
                f"{context_hint}\n\n"
                f"待聚合的下层摘要（共 {len(sources)} 条）：\n\n{joined}\n\n"
                f"请按规则输出 {level} 弧线摘要（覆盖范围：{arc_window}）。"
            )
            text = await model_gateway.generate_text(
                session,
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                task_type=f"summarize_arc_{level.lower()}",
                system_prompt=prompt,
                user_prompt=user_prompt,
                prompt_key=_PROMPT_KEY,
                prompt_version=_PROMPT_VERSION,
                temperature=0.3,
                metadata={"level": level, "arc_window": arc_window},
            )
            cleaned = (text or "").strip()
            if cleaned:
                return cleaned
        except Exception:  # noqa: BLE001 - 主路径失败必须回落
            _logger.warning(
                "hierarchical_summary_llm_failed",
                extra={"level": level, "arc_window": arc_window},
                exc_info=True,
            )
        return self._fallback_summary(sources)

    @staticmethod
    def _fallback_summary(sources: list[tuple[str, str]]) -> str:
        """纯拼接 fallback：按"标题：内容"换行，截断到 _MAX_FALLBACK_CHARS。"""
        joined = "\n".join(
            f"{title}：{content}".strip() for title, content in sources if content
        )
        if len(joined) > _MAX_FALLBACK_CHARS:
            joined = joined[:_MAX_FALLBACK_CHARS] + "…"
        return joined or "（暂无可用摘要）"

    @staticmethod
    async def _persist(
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        level: str,
        arc_window: str,
        source_type: str,
        source_id: str,
        memory_type: str,
        title: str,
        content: str,
        importance: int = 4,
    ) -> MemoryEntry:
        repo = MemoryRepository(session)
        # importance 在高层级偏高，体现"宏观信息更稀缺更重要"
        importance_by_level: dict[str, int] = {"L2": 4, "L3": 5, "L4": 6}
        entry = await repo.create(
            organization_id=organization_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            memory_type=memory_type,
            title=title,
            content=content,
            importance=importance_by_level.get(level, importance),
            level=level,
            arc_window=arc_window,
        )
        return entry


hierarchical_summarizer = HierarchicalSummarizer()


__all__ = ["HierarchicalSummarizer", "hierarchical_summarizer"]
