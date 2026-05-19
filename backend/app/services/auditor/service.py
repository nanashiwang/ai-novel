"""审稿服务。

输入：当前 scene + 最新 draft 内容。
输出：AuditResultContract（list of AuditIssueItem）。

设计：复用 ContextBuilder.build_for_scene_writing 拿到 bible/chapter/scene
等结构化上下文，加上"请审稿"指令；模型只负责找问题，不重写正文。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.schemas.story_generation import AuditResultContract
from app.services.context_builder.service import context_builder
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_AUDIT_SCENE = "audit/audit_scene"
_PROMPT_VERSION = "v1"


class AuditorService:
    async def audit_scene_draft(
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
        draft_content: str,
    ) -> AuditResultContract:
        prompt = prompt_manager.load(_PROMPT_AUDIT_SCENE, version=_PROMPT_VERSION)
        ctx = await context_builder.build_for_scene_writing(
            session,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
        )
        user_prompt = (
            ctx.to_prompt()
            + "\n\n## 待审稿正文\n"
            + draft_content
            + "\n\n## 任务指令\n"
            + "请审查上述正文是否违反以下任一类约束，并给出可立刻执行的修复建议：\n"
            + "- continuity：是否与故事圣经、之前 scenes 摘要存在情节/时间冲突\n"
            + "- character：人物动机、性格、弧光是否被违反\n"
            + "- world_rule：是否违反世界硬规则\n"
            + "- style：是否偏离风格守则\n"
            + "对每条问题给出 severity (low/medium/high)、description（一句话）、"
            + "suggested_fix（一句话）；正文若整体没问题，issues 返回空数组。"
            + "只返回 JSON。"
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="audit_scene",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=AuditResultContract.model_json_schema(),
            prompt_key=_PROMPT_AUDIT_SCENE,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "scene_id": scene.id,
                "chapter_id": chapter.id,
                "context_total_tokens": ctx.total_tokens,
            },
        )
        return AuditResultContract.model_validate(raw)


auditor_service = AuditorService()
