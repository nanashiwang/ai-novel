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

_PROMPT_REWRITE_SCENE = "writing/rewrite_scene"
_PROMPT_VERSION = "v1"


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
        issues_block = "\n".join(
            f"- [{issue.severity}/{issue.issue_type}] {issue.description}"
            + (f"  修复建议：{issue.suggested_fix}" if issue.suggested_fix else "")
            for issue in issues
        ) or "（审稿系统未给出问题，仅做风格打磨。）"

        user_prompt = (
            ctx.to_prompt()
            + "\n\n## 当前正文\n"
            + current_content
            + "\n\n## 待修复问题\n"
            + issues_block
            + "\n\n## 任务指令\n"
            + f"请基于以上上下文重新生成 scene #{scene.scene_index} 正文，"
            + f"目标字数约 {target_words} 字。要求：\n"
            + "- 修复每条问题的描述/建议，保持原情节走向\n"
            + "- 保留场景目标、冲突、揭示与钩子\n"
            + "- 不要在正文中输出 issue 编号或自我点评\n"
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
                continuity_notes=["mock 模式回退：rewrite 没能生成新正文，沿用原稿。"],
                unresolved_threads=[],
            )
        return draft


rewriter_service = RewriterService()
