"""正文自动后处理。

生成正文或重修正文之后、落库之前，跑一轮轻量自然化：
- 降低 AI 味；
- 保留剧情事实与防遗忘承接要求；
- 清理 Markdown 加粗/斜体等正文不应出现的标记。

服务采用 fail-soft：模型调用失败或返回异常时回退原文，避免后处理破坏主写作链路。
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chapter import Chapter
from app.models.continuity_issue import ContinuityIssue
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.story_state.prompting import (
    build_anti_forgetting_prompt_block,
    format_story_state_brief,
    load_story_state_items_by_id,
)

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "writing/postprocess_scene_draft"
_PROMPT_VERSION = "v1"

PostprocessStage = Literal["write", "rewrite"]


class DraftPostProcessorService:
    async def postprocess_scene_content(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        project: Project,
        spec: NovelSpec,
        chapter: Chapter,
        scene: Scene,
        content: str,
        target_words: int,
        stage: PostprocessStage,
        issues: list[ContinuityIssue] | None = None,
    ) -> str:
        """返回后处理正文；失败或关闭时返回原文。"""
        original = (content or "").strip()
        if not original:
            return content
        if not get_settings().draft_postprocess_enabled:
            return original

        try:
            anti_forgetting_block, anti_forgetting_meta = await build_anti_forgetting_prompt_block(
                session,
                organization_id=organization_id,
                project_id=project_id,
                chapter=chapter,
                scene=scene,
                purpose="writing",
            )
            issues_block = await self._format_issues_block(
                session,
                organization_id=organization_id,
                project_id=project_id,
                issues=issues or [],
            )
            system_prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
            polished = await model_gateway.generate_text(
                session,
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                task_type=(
                    "postprocess_rewrite_draft"
                    if stage == "rewrite"
                    else "postprocess_scene_draft"
                ),
                system_prompt=system_prompt,
                user_prompt=self._build_user_prompt(
                    project=project,
                    spec=spec,
                    chapter=chapter,
                    scene=scene,
                    content=original,
                    target_words=target_words,
                    stage=stage,
                    anti_forgetting_block=anti_forgetting_block,
                    issues_block=issues_block,
                ),
                prompt_key=_PROMPT_KEY,
                prompt_version=_PROMPT_VERSION,
                temperature=0.45,
                metadata={
                    "scene_id": scene.id,
                    "chapter_id": chapter.id,
                    "pipeline_step": "draft_postprocess",
                    "postprocess_stage": stage,
                    "input_chars": len(original),
                    "issue_count": len(issues or []),
                    **anti_forgetting_meta,
                },
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "draft_postprocess_failed",
                exc_info=True,
                extra={
                    "job_id": job_id,
                    "scene_id": scene.id,
                    "stage": stage,
                    "error": str(exc),
                },
            )
            return self._cleanup_markdown_emphasis(original)

        cleaned = self._cleanup_markdown_emphasis(polished)
        if not self._is_usable_output(cleaned, original):
            _logger.warning(
                "draft_postprocess_unusable_output",
                extra={
                    "job_id": job_id,
                    "scene_id": scene.id,
                    "stage": stage,
                    "input_chars": len(original),
                    "output_chars": len(cleaned),
                },
            )
            return self._cleanup_markdown_emphasis(original)
        return cleaned

    async def _format_issues_block(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        issues: list[ContinuityIssue],
    ) -> str:
        if not issues:
            return "（本次不是审稿重修，或暂无待修复问题。）"
        linked_state_ids = {
            issue.story_state_item_id
            for issue in issues
            if issue.story_state_item_id
        }
        linked_states = await load_story_state_items_by_id(
            session,
            organization_id=organization_id,
            project_id=project_id,
            state_item_ids=linked_state_ids,
        )
        lines: list[str] = []
        for issue in issues:
            line = f"- [{issue.severity}/{issue.issue_type}] {issue.description}"
            if issue.story_state_item_id:
                line += f"；story_state_item_id={issue.story_state_item_id}"
                linked = linked_states.get(issue.story_state_item_id)
                if linked is not None:
                    line += f"；关联关键状态：{format_story_state_brief(linked)}"
            if issue.suggested_fix:
                line += f"；修复建议：{issue.suggested_fix}"
            lines.append(line)
        return "\n".join(lines)

    def _build_user_prompt(
        self,
        *,
        project: Project,
        spec: NovelSpec,
        chapter: Chapter,
        scene: Scene,
        content: str,
        target_words: int,
        stage: PostprocessStage,
        anti_forgetting_block: str,
        issues_block: str,
    ) -> str:
        stage_label = "审稿重修后正文" if stage == "rewrite" else "初稿生成正文"
        style_parts = [
            spec.style_guide,
            f"题材：{project.genre}" if project.genre else "",
            f"目标读者：{project.target_reader}" if project.target_reader else "",
        ]
        style_guide = "\n".join(part.strip() for part in style_parts if part and part.strip())
        return (
            "## 处理阶段\n"
            + stage_label
            + "\n\n## 项目风格\n"
            + (style_guide or "自然中文类型小说语感，避免模板化表达。")
            + "\n\n## 章节与场景计划\n"
            + f"- 项目：{project.title}\n"
            + f"- 第 {chapter.chapter_index} 章：{chapter.title}\n"
            + f"- 章节目标：{chapter.goal or chapter.summary or '推进主线'}\n"
            + f"- 场景 {scene.scene_index}：{scene.title}\n"
            + f"- 场景目标：{scene.goal or scene.scene_purpose or '推进当前场景'}\n"
            + f"- 冲突：{scene.conflict or '保持场景内压力'}\n"
            + f"- 揭示：{scene.reveal or '按场景计划自然释放信息'}\n"
            + f"- 钩子：{scene.hook or '自然衔接下一步选择'}\n"
            + f"- 目标字数：约 {target_words} 字，后处理后不要大幅扩写或压缩。\n"
            + anti_forgetting_block
            + "\n\n## 待修复问题（重修时必须保持已修复，不得润回去）\n"
            + issues_block
            + "\n\n## 待自然化正文\n"
            + content
            + "\n\n## 任务指令\n"
            + "请把上面的正文处理成更自然的人话网文：更具体、更少解释、对白更像真人。"
            + "只允许修改表达方式，不允许改变剧情事实、关键设定、场景结果和审稿修复。"
            + "只输出处理后的正文纯文本。"
        )

    def _cleanup_markdown_emphasis(self, text: str) -> str:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:markdown|text)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"__(.*?)__", r"\1", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"(?<!\*)\*(?!\*)([^*\n]{1,120}?)(?<!\*)\*(?!\*)", r"\1", cleaned)
        cleaned = re.sub(r"(?<!_)_(?!_)([^_\n]{1,120}?)(?<!_)_(?!_)", r"\1", cleaned)
        return cleaned.strip()

    def _is_usable_output(self, output: str, original: str) -> bool:
        if not output.strip():
            return False
        if len(original) >= 200 and len(output) < len(original) * 0.35:
            return False
        lowered = output.lower()
        if "## 任务指令" in output or "待自然化正文" in output:
            return False
        if lowered.startswith("{") and lowered.endswith("}"):
            return False
        return True


draft_postprocessor_service = DraftPostProcessorService()
