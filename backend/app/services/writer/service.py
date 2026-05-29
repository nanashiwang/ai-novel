from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chapter import Chapter
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.schemas.story_generation import SceneDraftContract
from app.services.context_builder.service import context_builder
from app.services.model_gateway.providers import ModelJsonParseError
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.story_state.prompting import build_anti_forgetting_prompt_block
from app.services.writer.drafter import scene_drafter_agent
from app.services.writer.planner import scene_planner_agent
from app.services.writer.stylist import scene_stylist_agent

# 集中管理 prompt 路径与版本，便于升级时 model_calls 表同步记录真实版本。
# Sprint 13-B3：写作 prompt v2 强化人物口吻 + 场景节奏 + show-don't-tell。
_PROMPT_WRITE_SCENE = "writing/write_scene"
_PROMPT_VERSION = "v2"


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

        Sprint 4：通过 ContextBuilder.build_for_scene_writing 组装上下文。
        Sprint 14-C3：根据 settings.writer_pipeline_mode 在 single / multi 两条
        路径之间切换；公开签名保持不变，外层 activities.py 不需调整。
        """
        ctx = await context_builder.build_for_scene_writing(
            session,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
            previous_excerpt=previous_scene_excerpt,
        )
        ctx_prompt = ctx.to_prompt()
        anti_forgetting_block, anti_forgetting_meta = await build_anti_forgetting_prompt_block(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            purpose="writing",
        )
        if anti_forgetting_block:
            ctx_prompt = ctx_prompt + anti_forgetting_block

        settings = get_settings()
        if settings.writer_pipeline_mode == "multi":
            return await self._write_scene_draft_multi(
                session,
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                spec=spec,
                chapter=chapter,
                scene=scene,
                ctx_prompt=ctx_prompt,
                ctx_total_tokens=ctx.total_tokens,
                ctx_truncated=[s.label for s in ctx.segments if s.truncated],
                anti_forgetting_meta=anti_forgetting_meta,
                target_words=target_words,
            )
        return await self._write_scene_draft_single(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            chapter=chapter,
            scene=scene,
            ctx_prompt=ctx_prompt,
            ctx_total_tokens=ctx.total_tokens,
            ctx_truncated=[s.label for s in ctx.segments if s.truncated],
            anti_forgetting_meta=anti_forgetting_meta,
            target_words=target_words,
        )

    async def _write_scene_draft_single(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        chapter: Chapter,
        scene: Scene,
        ctx_prompt: str,
        ctx_total_tokens: int,
        ctx_truncated: list[str],
        anti_forgetting_meta: dict[str, object],
        target_words: int,
    ) -> SceneDraftContract:
        """原 single 模式：单次 generate_json 直接产 SceneDraftContract。"""
        prompt = prompt_manager.load(_PROMPT_WRITE_SCENE, version=_PROMPT_VERSION)
        user_prompt = (
            ctx_prompt
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
                    "pipeline_step": "single",
                    # 把 ContextBuilder 的诊断指标记到 metadata，便于运维侧观察预算分配
                    "context_total_tokens": ctx_total_tokens,
                    "context_truncated_segments": ctx_truncated,
                    **anti_forgetting_meta,
                },
            )
        except ModelJsonParseError as exc:
            # 远端 6ddded0 兜底：模型返回纯文本（未按 JSON schema）时
            # 直接把 raw_text 当作正文保存，避免整次 scene 写作 fail。
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

    async def _write_scene_draft_multi(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        spec: NovelSpec,
        chapter: Chapter,
        scene: Scene,
        ctx_prompt: str,
        ctx_total_tokens: int,
        ctx_truncated: list[str],
        anti_forgetting_meta: dict[str, object],
        target_words: int,
    ) -> SceneDraftContract:
        """multi 模式：planner → drafter → stylist 三步流水线。

        三步任意一步失败：fail-fast 抛错，外层 activities._revert_project_status_on_failure
        会处理回滚与 quota 释放。
        """
        # Step 1: planner
        beat_sheet = await scene_planner_agent.plan_beats(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            ctx_prompt=ctx_prompt,
            scene=scene,
            target_words=target_words,
            extra_metadata=anti_forgetting_meta,
        )
        if not beat_sheet.beats:
            raise ValueError("scene_planner_returned_no_beats")

        # Step 2: drafter
        draft_markdown = await scene_drafter_agent.draft_by_beats(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            ctx_prompt=ctx_prompt,
            scene=scene,
            beats=beat_sheet.beats,
            total_target_words=beat_sheet.total_target_words or target_words,
            extra_metadata=anti_forgetting_meta,
        )
        if not draft_markdown.strip():
            raise ValueError("scene_drafter_returned_empty_markdown")

        # Step 3: stylist（style_guide 为空时内部会 noop 返回 draft，不消耗 token）
        style_guide = (spec.style_guide or "").strip()
        polished = await scene_stylist_agent.polish(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            scene=scene,
            draft=draft_markdown,
            style_guide=style_guide,
        )

        # 包装回 SceneDraftContract。保留 chapter / ctx 诊断到 continuity_notes，
        # 便于运维侧排查。
        notes = [
            f"multi-agent pipeline: planner({len(beat_sheet.beats)} beats) → "
            f"drafter → stylist({'noop' if polished is draft_markdown else 'applied'})",
        ]
        if ctx_truncated:
            notes.append(
                "context_truncated_segments: " + ",".join(ctx_truncated)
            )
        return SceneDraftContract(
            scene_id=scene.id,
            title=scene.title,
            content=polished,
            word_count=len(polished),
            continuity_notes=notes,
            unresolved_threads=[scene.hook] if scene.hook else [],
        )

    def _fallback_scene_content(self, chapter: Chapter, scene: Scene, target_words: int) -> str:
        return (
            f"《{chapter.title}》里的“{scene.title}”开始于{scene.time_marker or '一个关键时刻'}。"
            f"地点是{scene.location or '故事的核心地点'}，"
            f"入场状态是{scene.entry_state or '承接上一场压力'}，"
            f"人物围绕“{scene.goal or '当前目标'}”行动。"
            f"冲突很快浮出水面：{scene.conflict or '他们的目标与现实阻力发生碰撞'}。"
            f"本场必须推进："
            f"{'、'.join(scene.must_include or []) or scene.scene_purpose or '本章目标'}；"
            f"需要避免：{'、'.join(scene.must_avoid or []) or '重复上一场已解决的信息'}。"
            f"情绪从{scene.emotion_start or '克制'}转向{scene.emotion_end or '紧绷'}，"
            f"并揭示出：{scene.reveal or '一个会改变后续判断的新事实'}。"
            f"退场状态是{scene.exit_state or '带着新的压力进入下一场'}，"
            f"场景末尾留下钩子：{scene.hook or '下一步选择变得无法回避'}。"
            f"\n\n目标篇幅约 {target_words} 字；当前为流水线占位正文，可在真实模型接入后替换。"
        )


writer_service = WriterService()
