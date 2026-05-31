"""场景重写服务。

输入：当前 scene + 当前 draft + 待修复的 issues 列表。
输出：SceneDraftContract（新的 draft 候选）。

设计：复用 ContextBuilder.build_for_scene_writing；在 user_prompt 中附加
"以下是当前正文 + 待修复问题，请整体重写"指令。模型应当尊重 issues 的
suggested_fix，但允许小幅措辞调整。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.continuity_issue import ContinuityIssue
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.schemas.story_generation import SceneDraftContract
from app.services.context_builder.service import context_builder
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.story_state.prompting import (
    build_anti_forgetting_prompt_block,
    format_story_state_brief,
    load_story_state_items_by_id,
)

_PROMPT_REWRITE_SCENE = "writing/rewrite_scene"
# Sprint 13-B3：与 write_scene v2 对齐，同样强化人物口吻 + 节奏 + show 优先。
_PROMPT_VERSION = "v2"


class RewriterService:
    async def rewrite_scene_draft(
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
        current_content: str,
        issues: list[ContinuityIssue],
        target_words: int = 1200,
    ) -> SceneDraftContract:
        prompt = prompt_manager.load(_PROMPT_REWRITE_SCENE, version=_PROMPT_VERSION)
        ctx = await context_builder.build_for_scene_writing(
            session,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
        )
        anti_forgetting_block, anti_forgetting_meta = await build_anti_forgetting_prompt_block(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            purpose="writing",
        )
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
        issues_block = "\n".join(
            self._format_issue_line(issue, linked_states)
            for issue in issues
        ) or "（审稿系统未给出问题，仅做风格打磨。）"
        high_issue_count = sum(
            1 for issue in issues if (issue.severity or "").lower() == "high"
        )
        high_issue_block = self._format_high_issue_block(issues, linked_states)

        user_prompt = (
            ctx.to_prompt()
            + anti_forgetting_block
            + "\n\n## 当前正文\n"
            + current_content
            + "\n\n## 待修复问题\n"
            + issues_block
            + high_issue_block
            + "\n\n## 任务指令\n"
            + f"请基于以上上下文重新生成 scene #{scene.scene_index} 正文，"
            + f"目标字数约 {target_words} 字。要求：\n"
            + "- 修复每条问题的描述/建议，保持原情节走向；但当原正文与问题修复冲突时，优先修复问题\n"
            + "- high 严重度问题是硬约束，必须逐条实质改写，不能只换词或弱化表述\n"
            + "- 新稿不得再次触发同类 high 问题；涉及提前出场、提前知情、设定冲突时，必须删除或改成当前场景允许的信息\n"
            + "- 严格遵守“写作防遗忘承接清单”，尤其是待修复问题关联的关键状态项\n"
            + "- 保留场景目标、冲突、揭示与钩子\n"
            + "- 不要在正文中输出 issue 编号或自我点评\n"
            + "- 不要在正文中输出 story_state_item_id、requirement_id 或清单文字\n"
            + "- 只返回 JSON。"
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="rewrite_scene",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=SceneDraftContract.model_json_schema(),
            prompt_key=_PROMPT_REWRITE_SCENE,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "scene_id": scene.id,
                "chapter_id": chapter.id,
                "context_total_tokens": ctx.total_tokens,
                "issue_count": len(issues),
                "high_issue_count": high_issue_count,
                "linked_story_state_issue_count": len(linked_state_ids),
                **anti_forgetting_meta,
            },
        )
        draft = SceneDraftContract.model_validate(
            {**raw, "scene_id": raw.get("scene_id") or scene.id}
        )
        if not draft.content:
            # 兜底：返回原文 + 注释，避免空内容污染版本链
            draft = SceneDraftContract(
                scene_id=scene.id,
                title=scene.title,
                content=current_content,
                word_count=len(current_content),
                continuity_notes=["模型返回空正文，已沿用原稿，建议重新生成。"],
                unresolved_threads=[],
            )
        return draft

    def _format_issue_line(
        self,
        issue: ContinuityIssue,
        linked_states: dict[str, object],
    ) -> str:
        severity = (issue.severity or "unknown").lower()
        label = {
            "high": "硬约束/必须修复",
            "medium": "重点修复",
            "low": "修正优化",
        }.get(severity, "待修复")
        line = f"- [{severity}/{issue.issue_type}]【{label}】{issue.description}"
        if issue.story_state_item_id:
            line += f"；story_state_item_id={issue.story_state_item_id}"
            linked = linked_states.get(issue.story_state_item_id)
            if linked is not None:
                line += f"；关联关键状态：{format_story_state_brief(linked)}"
        if issue.suggested_fix:
            line += f"  修复建议：{issue.suggested_fix}"
        if severity == "high":
            line += "  硬性处理：若当前正文与本条冲突，必须改写冲突段落；新稿不能再次出现同类问题。"
        return line

    def _format_high_issue_block(
        self,
        issues: list[ContinuityIssue],
        linked_states: dict[str, object],
    ) -> str:
        high_issues = [
            issue for issue in issues if (issue.severity or "").lower() == "high"
        ]
        if not high_issues:
            return ""
        lines = [
            "\n\n## 高危问题硬约束",
            "以下 high 严重度问题必须优先修复。若与原正文、局部气氛描写或支线戏份冲突，以本节为准：",
        ]
        lines.extend(self._format_issue_line(issue, linked_states) for issue in high_issues)
        lines.append(
            "修复自检：生成前确认这些问题在新稿中已被明确删除、改写或用当前场景允许的信息闭合。"
        )
        return "\n".join(lines)


rewriter_service = RewriterService()
