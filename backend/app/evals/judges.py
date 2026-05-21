"""LLM-as-judge：4 维评分。

设计：
- 默认走 stub（环境无 OPENAI_API_KEY 或 runner 传入 disabled=True 时），
  评分一律 3.0，保证 CI 可重现且不依赖外部 key
- 真实路径走 model_gateway.generate_json，并落 ModelCall 日志（便于 cost
  追踪与回溯 prompt 版本）
- 维度刻意控制在 4 个，避免维度爆炸导致打分语义模糊
"""
from __future__ import annotations

import os
from typing import Any

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import APIModel
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

JUDGE_PROMPT_KEY = "eval/judge_scene"
JUDGE_PROMPT_VERSION = "v1"

# 评分上下限；任何越界打分会被夹回区间，避免离群拉爆均值
_MIN_SCORE = 0.0
_MAX_SCORE = 5.0
_STUB_SCORE = 3.0  # 中位值，表示"未跑真模型"的中性占位


class JudgmentContract(APIModel):
    """4 维评分契约。"""

    coherence: float = Field(default=_STUB_SCORE, ge=_MIN_SCORE, le=_MAX_SCORE)
    dialogue_naturalness: float = Field(default=_STUB_SCORE, ge=_MIN_SCORE, le=_MAX_SCORE)
    pacing: float = Field(default=_STUB_SCORE, ge=_MIN_SCORE, le=_MAX_SCORE)
    show_dont_tell: float = Field(default=_STUB_SCORE, ge=_MIN_SCORE, le=_MAX_SCORE)
    comments: str = ""
    is_stub: bool = False  # True 表示该评分来自 stub（未调用真实 LLM）

    def aggregate(self) -> float:
        """4 维等权平均，便于一眼看总体质量。"""
        return round(
            (self.coherence + self.dialogue_naturalness + self.pacing + self.show_dont_tell) / 4.0,
            3,
        )


def _stub_judgment(reason: str = "judge_disabled") -> JudgmentContract:
    """生成 stub 评分。所有维度=3.0，comments 记录原因。"""
    return JudgmentContract(
        coherence=_STUB_SCORE,
        dialogue_naturalness=_STUB_SCORE,
        pacing=_STUB_SCORE,
        show_dont_tell=_STUB_SCORE,
        comments=f"[stub] {reason}",
        is_stub=True,
    )


def _clamp(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return _STUB_SCORE
    return max(_MIN_SCORE, min(_MAX_SCORE, score))


async def judge_scene(
    session: AsyncSession | None,
    *,
    scene_content: str,
    scene_plan: dict[str, Any] | None = None,
    bible_summary: str = "",
    organization_id: str = "eval-system",
    project_id: str | None = None,
    job_id: str | None = None,
    disabled: bool = False,
) -> JudgmentContract:
    """对单个 scene 文本打分。

    disabled=True 或 OPENAI_API_KEY 缺失时直接返回 stub 评分，**不**调用 LLM。
    session 在真实链路用于落 ModelCall 日志；stub 路径下允许为 None。
    """
    if disabled:
        return _stub_judgment("judge_disabled by caller")
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        return _stub_judgment("no LLM api key in env")
    if session is None:
        # 真实链路必须有 session 才能落日志；缺失时退化到 stub 而非抛错
        return _stub_judgment("no db session provided")

    system_prompt = prompt_manager.load(JUDGE_PROMPT_KEY, version=JUDGE_PROMPT_VERSION)
    user_prompt = _build_user_prompt(
        scene_content=scene_content,
        scene_plan=scene_plan or {},
        bible_summary=bible_summary,
    )
    raw = await model_gateway.generate_json(
        session,
        organization_id=organization_id,
        project_id=project_id,
        job_id=job_id,
        task_type="eval_judge_scene",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=JudgmentContract.model_json_schema(),
        prompt_key=JUDGE_PROMPT_KEY,
        prompt_version=JUDGE_PROMPT_VERSION,
        temperature=0.0,
    )
    return JudgmentContract(
        coherence=_clamp(raw.get("coherence")),
        dialogue_naturalness=_clamp(raw.get("dialogue_naturalness")),
        pacing=_clamp(raw.get("pacing")),
        show_dont_tell=_clamp(raw.get("show_dont_tell")),
        comments=str(raw.get("comments") or "")[:200],
        is_stub=False,
    )


def _build_user_prompt(
    *,
    scene_content: str,
    scene_plan: dict[str, Any],
    bible_summary: str,
) -> str:
    """拼接 judge 的 user prompt。

    保持极简：bible 摘要 + scene plan + 正文。
    更复杂的 grounding（人物状态、前文摘要）留待章节级评测扩展。
    """
    parts: list[str] = []
    if bible_summary:
        parts.append(f"## 故事圣经摘要\n{bible_summary.strip()}")
    if scene_plan:
        plan_lines = [f"- {key}: {value}" for key, value in scene_plan.items() if value]
        if plan_lines:
            parts.append("## Scene Plan\n" + "\n".join(plan_lines))
    parts.append("## Scene 正文\n" + (scene_content or "").strip())
    parts.append(
        "## 任务\n请按 system prompt 中定义的 4 维评分，只输出 JSON。"
    )
    return "\n\n".join(parts)
