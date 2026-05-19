from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.project import NovelSpec
from app.models.scene import Scene
from app.schemas.story_generation import SceneDraftContract
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
        spec: NovelSpec,
        chapter: Chapter,
        scene: Scene,
        previous_scene_excerpt: str = "",
        target_words: int = 1200,
    ) -> SceneDraftContract:
        prompt = prompt_manager.load(_PROMPT_WRITE_SCENE, version=_PROMPT_VERSION)
        user_prompt = (
            "请根据故事圣经、章节大纲和 scene card 写出一个完整场景正文。\n"
            f"故事圣经：{spec.premise}\n"
            f"主题：{spec.theme}\n"
            f"类型/语气：{spec.genre} / {spec.tone}\n"
            f"叙事视角：{spec.narrative_pov}\n"
            f"风格约束：{spec.style_guide}\n"
            f"硬约束：{spec.constraints}\n"
            f"章节：第 {chapter.chapter_index} 章《{chapter.title}》\n"
            f"章节摘要：{chapter.summary}\n"
            f"章节目标：{chapter.goal}\n"
            f"章节冲突：{chapter.conflict}\n"
            f"场景：{scene.title}\n"
            f"地点/时间：{scene.location} / {scene.time_marker}\n"
            f"人物：{scene.characters}\n"
            f"场景目标：{scene.goal}\n"
            f"微冲突：{scene.conflict}\n"
            f"情绪变化：{scene.emotion_start} -> {scene.emotion_end}\n"
            f"揭示：{scene.reveal}\n"
            f"结尾钩子：{scene.hook}\n"
            f"上一场景结尾片段：{previous_scene_excerpt}\n"
            f"目标字数：{target_words}\n"
            "要求：正文有画面、有动作、有对话，避免总结式大纲；只返回 JSON。"
        )
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
            metadata={"scene_id": scene.id, "chapter_id": chapter.id},
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
                continuity_notes=["mock 模式生成的占位正文，后续可用真实模型重写。"],
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
