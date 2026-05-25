from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.schemas.story_generation import SceneDraftContract
from app.services.context_builder.service import context_builder
from app.services.model_gateway.providers import ModelJsonParseError
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

# 集中管理 prompt 路径与版本，便于升级时 model_calls 表同步记录真实版本。
_PROMPT_WRITE_SCENE = "writing/write_scene"
_PROMPT_VERSION = "v1"


class WriterService:
    async def write_scene(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        scene_id: str,
    ) -> str:
        prompt = prompt_manager.load(_PROMPT_WRITE_SCENE, version=_PROMPT_VERSION)
        return await model_gateway.generate_text(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="write_scene",
            system_prompt=prompt,
            user_prompt=f"以 scene 为最小单位生成正文，scene_id={scene_id}",
            prompt_key=_PROMPT_WRITE_SCENE,
            prompt_version=_PROMPT_VERSION,
            metadata={"scene_id": scene_id},
        )

    async def write_scene_draft(
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
        previous_scene_excerpt: str = "",
        target_words: int = 1200,
    ) -> SceneDraftContract:
        """生成单场景正文草稿。

        Sprint 4：通过 ContextBuilder.build_for_scene_writing 组装上下文，
        替代之前的字符串拼接。ContextBuilder 输出已经按 7 段优先级+token
        budget 处理，writer 只需追加"任务指令"段。
        """
        prompt = prompt_manager.load(_PROMPT_WRITE_SCENE, version=_PROMPT_VERSION)
        ctx = await context_builder.build_for_scene_writing(
            session,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            previous_excerpt=previous_scene_excerpt,
        )
        user_prompt = (
            ctx.to_prompt()
            + "\n\n## 任务指令\n"
            + f"请根据以上上下文写出场景 #{scene.scene_index} 的完整正文，"
            + f"目标字数约 {target_words} 字。\n"
            + "要求：正文有画面、有动作、有对话，避免总结式大纲；"
            + "只返回 JSON，字段必须可直接落库。"
        )
        try:
            raw = await model_gateway.generate_json(
                session,
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                task_type="write_scene_draft",
                system_prompt=prompt,
                user_prompt=user_prompt,
                schema=SceneDraftContract.model_json_schema(),
                prompt_key=_PROMPT_WRITE_SCENE,
                prompt_version=_PROMPT_VERSION,
                metadata={
                    "scene_id": scene.id,
                    "chapter_id": chapter.id,
                    # 把 ContextBuilder 的诊断指标记到 metadata，便于运维侧观察预算分配
                    "context_total_tokens": ctx.total_tokens,
                    "context_truncated_segments": [
                        s.label for s in ctx.segments if s.truncated
                    ],
                },
            )
        except ModelJsonParseError as exc:
            content = exc.raw_text.strip()
            if not content:
                raise
            return SceneDraftContract(
                scene_id=scene.id,
                title=scene.title,
                content=content,
                word_count=len(content),
                continuity_notes=["模型返回纯文本，已按正文兜底保存。"],
                unresolved_threads=[scene.hook] if scene.hook else [],
            )
        draft = SceneDraftContract.model_validate(
            {**raw, "scene_id": raw.get("scene_id") or scene.id}
        )
        if not draft.content:
            content = self._fallback_scene_content(chapter, scene, target_words)
            draft = SceneDraftContract(
                scene_id=scene.id,
                title=scene.title,
                content=content,
                word_count=len(content),
                continuity_notes=["模型返回空正文，已生成临时占位正文，建议重新生成。"],
                unresolved_threads=[scene.hook] if scene.hook else [],
            )
        return draft

    def _fallback_scene_content(self, chapter: Chapter, scene: Scene, target_words: int) -> str:
        return (
            f"《{chapter.title}》里的“{scene.title}”开始于{scene.time_marker or '一个关键时刻'}。"
            f"地点是{scene.location or '故事的核心地点'}，"
            f"人物围绕“{scene.goal or '当前目标'}”行动。"
            f"冲突很快浮出水面：{scene.conflict or '他们的目标与现实阻力发生碰撞'}。"
            f"情绪从{scene.emotion_start or '克制'}转向{scene.emotion_end or '紧绷'}，"
            f"并揭示出：{scene.reveal or '一个会改变后续判断的新事实'}。"
            f"场景末尾留下钩子：{scene.hook or '下一步选择变得无法回避'}。"
            f"\n\n目标篇幅约 {target_words} 字；当前为流水线占位正文，可在真实模型接入后替换。"
        )


writer_service = WriterService()
