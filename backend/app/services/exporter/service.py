"""场景导出服务。

Sprint 5-B 实现：把项目下所有 chapter 的每个 scene 取最新 draft，拼成
Markdown / TXT，返回 (content, size) 元组。不调 LLM、无 quota、同步操作。

Sprint 4-C 起 draft.content 可能是 markdown 字符串（content_format='markdown'），
导出 markdown 时直接拼接；导出 TXT 时经过 markdown_stripper 转 plain。
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.project import Project
from app.models.scene import Scene
from app.repositories import (
    ChapterRepository,
    DraftVersionRepository,
    SceneRepository,
)

from .markdown_stripper import strip_markdown

ExportFormat = Literal["markdown", "txt"]


class ExporterService:
    async def export_project(
        self,
        session: AsyncSession,
        *,
        project: Project,
        export_format: ExportFormat = "markdown",
    ) -> tuple[str, int]:
        """生成 project 全文导出内容。

        返回 (content, byte_size)。无 chapter 时返回仅含标题的占位文档；
        无 scene 或无 draft 时跳过该章。Markdown / TXT 共享主拼接流程，
        差别只在标题前缀和分隔符。
        """
        chapter_repo = ChapterRepository(session)
        scene_repo = SceneRepository(session)
        draft_repo = DraftVersionRepository(session)

        chapters = list(
            await chapter_repo.list(
                organization_id=project.organization_id,
                project_id=project.id,
                order_by=Chapter.chapter_index.asc(),
            )
        )
        scenes_by_chapter = await self._group_scenes_by_chapter(
            scene_repo, project, chapters
        )
        drafts_by_scene = await self._latest_drafts_by_scene(draft_repo, project)

        if export_format == "markdown":
            content = self._render_markdown(project, chapters, scenes_by_chapter, drafts_by_scene)
        else:
            content = self._render_txt(project, chapters, scenes_by_chapter, drafts_by_scene)
        return content, len(content.encode("utf-8"))

    # ------------------------------------------------------------------
    # 数据组装：把全表查询折叠成 dict，避免 N+1
    # ------------------------------------------------------------------

    async def _group_scenes_by_chapter(
        self,
        scene_repo: SceneRepository,
        project: Project,
        chapters: list[Chapter],
    ) -> dict[str, list[Scene]]:
        all_scenes = list(
            await scene_repo.list(
                organization_id=project.organization_id,
                project_id=project.id,
            )
        )
        by_chapter: dict[str, list[Scene]] = {c.id: [] for c in chapters}
        for s in all_scenes:
            if s.chapter_id in by_chapter:
                by_chapter[s.chapter_id].append(s)
        for scenes in by_chapter.values():
            scenes.sort(key=lambda x: x.scene_index)
        return by_chapter

    async def _latest_drafts_by_scene(
        self,
        draft_repo: DraftVersionRepository,
        project: Project,
    ) -> dict[str, DraftVersion]:
        """取该项目所有 scenes 的最新 draft（按 created_at desc 排序后取首条）。"""
        all_drafts = list(
            await draft_repo.list(
                organization_id=project.organization_id,
                project_id=project.id,
            )
        )
        latest: dict[str, DraftVersion] = {}
        # base list 默认 created_at desc，所以遍历时第一个出现的是最新
        for d in all_drafts:
            if d.scene_id and d.scene_id not in latest:
                latest[d.scene_id] = d
        return latest

    # ------------------------------------------------------------------
    # 渲染：Markdown 与 TXT 共用结构，差别在标题前缀和分隔符
    # ------------------------------------------------------------------

    def _render_markdown(
        self,
        project: Project,
        chapters: list[Chapter],
        scenes_by_chapter: dict[str, list[Scene]],
        drafts_by_scene: dict[str, DraftVersion],
    ) -> str:
        lines: list[str] = []
        lines.append(f"# {project.title}\n")
        meta_bits = []
        if project.genre:
            meta_bits.append(f"体裁：{project.genre}")
        if project.target_word_count:
            meta_bits.append(f"目标字数：{project.target_word_count}")
        if project.target_reader:
            meta_bits.append(f"目标读者：{project.target_reader}")
        if meta_bits:
            lines.append("> " + " · ".join(meta_bits) + "\n")
        if not chapters:
            lines.append("\n*该项目尚未生成任何章节。*\n")
            return "\n".join(lines)
        for chapter in chapters:
            lines.append(f"\n## 第 {chapter.chapter_index} 章 · {chapter.title}\n")
            if chapter.summary:
                lines.append(f"> {chapter.summary}\n")
            scenes = scenes_by_chapter.get(chapter.id, [])
            if not scenes:
                lines.append("\n*该章节尚未拆分场景。*\n")
                continue
            for scene in scenes:
                lines.append(f"\n### 场景 {scene.scene_index} · {scene.title}\n")
                draft = drafts_by_scene.get(scene.id)
                if draft and draft.content:
                    # markdown / text 在 markdown 导出场景下都可以直接拼接：
                    # text 是 markdown 的合法子集（无标记），markdown 自然保留格式
                    lines.append("\n" + draft.content + "\n")
                else:
                    lines.append("\n*该场景尚未生成正文。*\n")
        return "\n".join(lines)

    def _render_txt(
        self,
        project: Project,
        chapters: list[Chapter],
        scenes_by_chapter: dict[str, list[Scene]],
        drafts_by_scene: dict[str, DraftVersion],
    ) -> str:
        sep_outer = "=" * 60
        sep_inner = "-" * 40
        lines: list[str] = [project.title, sep_outer, ""]
        if not chapters:
            lines.append("该项目尚未生成任何章节。")
            return "\n".join(lines)
        for chapter in chapters:
            lines.append(f"\n{sep_outer}")
            lines.append(f"第 {chapter.chapter_index} 章 · {chapter.title}")
            lines.append(sep_outer)
            scenes = scenes_by_chapter.get(chapter.id, [])
            if not scenes:
                lines.append("\n（该章节尚未拆分场景）")
                continue
            for scene in scenes:
                lines.append(f"\n{sep_inner}")
                lines.append(f"场景 {scene.scene_index} · {scene.title}")
                lines.append(sep_inner)
                draft = drafts_by_scene.get(scene.id)
                if draft and draft.content:
                    lines.append("")
                    # TXT 导出剥离 markdown 标记，确保阅读体验为纯文本；
                    # 旧 'text' 数据走 strip 是无副作用的（无标记可剥）
                    if getattr(draft, "content_format", "text") == "markdown":
                        lines.append(strip_markdown(draft.content))
                    else:
                        lines.append(draft.content)
                else:
                    lines.append("\n（该场景尚未生成正文）")
        return "\n".join(lines) + "\n"


exporter_service = ExporterService()
