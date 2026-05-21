"""场景风格统一 agent（stylist）。

Sprint 14-C3 多 agent 场景写作流水线第 3 步：对 drafter 的 Markdown 草稿做
风格统一润色（用词/句长/对白口吻），**不改情节、不改 reveal/hook**。

设计要点：
- 输入：drafter 输出的 Markdown 全文 + 项目 style_guide（来自 NovelSpec.style_guide
  或 BuiltContext 的 hard_constraints 段，由调用方决定）
- 输出：润色后的 Markdown
- noop 兜底：若 style_guide 为空，直接返回 draft（不消耗 token、不写 model_call）
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene import Scene
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_KEY = "writing/stylist"
_PROMPT_VERSION = "v1"


class SceneStylistAgent:
    """风格统一润色。"""

    async def polish(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        scene: Scene,
        draft: str,
        style_guide: str,
    ) -> str:
        # style_guide 为空时不调模型，避免一次无意义的 token 消耗。
        # 调用方 orchestrator 可以根据返回值是否变化判断是否真正润色。
        if not style_guide.strip() or not draft.strip():
            return draft

        system_prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
        user_prompt = (
            "## 项目 style_guide\n"
            + style_guide.strip()
            + "\n\n## 待润色 Markdown 正文\n"
            + draft
            + "\n\n## 任务指令\n"
            + "请仅做用词、句长、对白口吻的统一润色，严禁修改情节、reveal、hook。"
            + "只返回润色后的 Markdown，不要解释。"
        )
        polished = await model_gateway.generate_text(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="write_scene_polish",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "scene_id": scene.id,
                "pipeline_step": "stylist",
                "input_chars": len(draft),
            },
        )
        # 极端情况：模型返回空串。回退到 draft，避免下游 word_count=0 的回退占位逻辑。
        return polished.strip() or draft


scene_stylist_agent = SceneStylistAgent()
