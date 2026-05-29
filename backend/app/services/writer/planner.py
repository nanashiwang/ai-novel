"""场景节奏规划 agent（planner）。

Sprint 14-C3 多 agent 场景写作流水线第 1 步：把单个 scene 拆成 4~8 个 beat。
产出 BeatSheetContract，供下游 drafter 按 beat 写正文。

设计要点：
- 输入：ContextBuilder 已经组装好的 ctx_prompt（包含 hard_constraints / task /
  characters / world_rules / plot_threads / recent_summary / memory_recall 等
  10 段），加上当前 scene 与目标字数
- 输出：BeatSheetContract（model_gateway.generate_json + JSON schema 验证）
- 失败兜底：若模型返回 0 beat 或字段缺失，由上层 orchestrator 判定 fail-fast
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene import Scene
from app.schemas.story_generation import BeatSheetContract
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_KEY = "writing/plan_beats"
_PROMPT_VERSION = "v1"


class ScenePlannerAgent:
    """对单 scene 做 beat 级分解。"""

    async def plan_beats(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        ctx_prompt: str,
        scene: Scene,
        target_words: int,
        extra_metadata: dict[str, object] | None = None,
    ) -> BeatSheetContract:
        system_prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
        user_prompt = (
            ctx_prompt
            + "\n\n## 任务指令\n"
            + f"请把场景 #{scene.scene_index}（{scene.title}）拆成 4 到 8 个 beat。"
            + f"全部 beat 的 target_words 之和应约为 {target_words} 字。"
            + "严格按 BeatSheetContract schema 输出 JSON，不要附加解释。"
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="write_scene_plan_beats",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=BeatSheetContract.model_json_schema(),
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "scene_id": scene.id,
                "pipeline_step": "planner",
                "target_words": target_words,
                **(extra_metadata or {}),
            },
        )
        beat_sheet = BeatSheetContract.model_validate(raw)
        # 兜底：若模型给的 total_target_words 为 0，则用各 beat 之和补齐。
        if beat_sheet.total_target_words <= 0 and beat_sheet.beats:
            beat_sheet.total_target_words = sum(b.target_words for b in beat_sheet.beats)
        return beat_sheet


scene_planner_agent = ScenePlannerAgent()
