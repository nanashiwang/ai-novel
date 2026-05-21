"""场景正文执笔 agent（drafter）。

Sprint 14-C3 多 agent 场景写作流水线第 2 步：根据 planner 产出的 BeatSheet
逐 beat 写 Markdown 正文。

设计要点：
- 输入：ctx_prompt（同 planner）、scene、planner 输出的 beats
- 输出：纯 Markdown 字符串（不带 JSON 包装、不带 beat 标签元信息）
- 通过 generate_text 调用，task_type="write_scene_draft_text" 与 single 模式
  的 "write_scene_draft" 区分，便于 metrics 拆解多 agent 流水线消耗
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene import Scene
from app.schemas.story_generation import BeatItem
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_KEY = "writing/draft_by_beats"
_PROMPT_VERSION = "v1"


def _format_beat_for_prompt(beat: BeatItem) -> str:
    """把单个 beat 渲染成给模型看的提示片段。

    drafter 提示里要让模型清楚"按顺序、不许漏"，因此每个 beat 都加上 index
    与 target_words；purpose/action/dialog_hint/reaction 列在下方便于对照。
    """
    lines = [
        f"### Beat {beat.index} （{beat.purpose}） — 目标 {beat.target_words} 字",
        f"- action: {beat.action}",
    ]
    if beat.dialog_hint:
        lines.append(f"- dialog_hint: {beat.dialog_hint}")
    if beat.reaction:
        lines.append(f"- reaction: {beat.reaction}")
    return "\n".join(lines)


class SceneDrafterAgent:
    """根据 BeatSheet 写 Markdown 正文。"""

    async def draft_by_beats(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        ctx_prompt: str,
        scene: Scene,
        beats: list[BeatItem],
        total_target_words: int,
    ) -> str:
        if not beats:
            # fail-fast：planner 失败时上层应该拦截，这里再加一道防线。
            raise ValueError("scene_drafter_empty_beats")

        system_prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
        beat_block = "\n\n".join(_format_beat_for_prompt(b) for b in beats)
        user_prompt = (
            ctx_prompt
            + "\n\n## Beat Sheet（必须按顺序逐段写，禁止漏 beat）\n"
            + beat_block
            + "\n\n## 任务指令\n"
            + f"请按上面 {len(beats)} 个 beat 顺序，写出场景 #{scene.scene_index} "
            + f"（{scene.title}）的完整 Markdown 正文，"
            + f"目标总字数约 {total_target_words} 字。"
            + "只返回正文 Markdown，不要 JSON、不要 beat 编号、不要任何脚手架。"
        )
        return await model_gateway.generate_text(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="write_scene_draft_text",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "scene_id": scene.id,
                "pipeline_step": "drafter",
                "beat_count": len(beats),
                "total_target_words": total_target_words,
            },
        )


scene_drafter_agent = SceneDrafterAgent()
