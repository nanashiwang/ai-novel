"""从 scene 正文反推时间字段，直接写回 scenes 表（Sprint 17-B B1）。

与 plot_thread / world / character extract 同模式，但目标表是 scenes
本身的 3 个新字段（in_story_day_offset / time_of_day / duration_minutes），
不走 revision 链。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.scene import Scene
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "temporal/extract_state"
_PROMPT_VERSION = "v1"

_ALLOWED_TIME_OF_DAY = {
    "dawn",
    "morning",
    "noon",
    "afternoon",
    "evening",
    "dusk",
    "night",
}


def _extract_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "in_story_day_offset": {"type": "integer", "minimum": 0},
            "time_of_day": {
                "type": "string",
                "enum": sorted(_ALLOWED_TIME_OF_DAY),
            },
            "duration_minutes": {"type": "integer", "minimum": 0},
            "reason": {"type": "string"},
        },
        "required": ["in_story_day_offset", "time_of_day", "duration_minutes"],
    }


async def _previous_temporal_state(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    current_scene: Scene,
) -> dict[str, Any] | None:
    """取该项目最大 in_story_day_offset 的已记录 scene（排除当前场）。"""
    stmt = (
        select(Scene)
        .where(
            Scene.organization_id == organization_id,
            Scene.project_id == project_id,
            Scene.id != current_scene.id,
            Scene.in_story_day_offset.isnot(None),
        )
        .order_by(Scene.in_story_day_offset.desc())
        .limit(1)
    )
    prev = (await session.execute(stmt)).scalars().first()
    if not prev:
        return None
    return {
        "scene_title": prev.title,
        "in_story_day_offset": prev.in_story_day_offset,
        "time_of_day": prev.time_of_day,
        "duration_minutes": prev.duration_minutes,
    }


async def extract_temporal_state_from_scene(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    job_id: str | None,
    chapter: Chapter,
    scene: Scene,
    draft: DraftVersion,
) -> dict[str, Any]:
    """反推当前场的 3 个时间字段并写回 scenes 表。

    失败 swallow + warn，绝不阻断主写作流程。
    """
    if not draft or not draft.content:
        return {"updated": False, "skipped": "no_draft"}

    previous = await _previous_temporal_state(
        session,
        organization_id=organization_id,
        project_id=project_id,
        current_scene=scene,
    )
    scene_payload = {
        "chapter_index": chapter.chapter_index,
        "chapter_title": chapter.title,
        "scene_index": scene.scene_index,
        "scene_title": scene.title,
        "time_marker": scene.time_marker,
        "location": scene.location,
        "draft_excerpt": (draft.content or "")[:6000],
    }
    try:
        prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="extract_temporal_state",
            system_prompt=prompt
            or "你是故事时间线追踪助手，请基于上一场状态与本场正文输出 JSON。",
            user_prompt=(
                "【上一场已记录的时间状态】\n"
                + (
                    json.dumps(previous, ensure_ascii=False)
                    if previous
                    else "（无：本场可能是开篇，请把 in_story_day_offset 设为 0）"
                )
                + "\n\n【当前 scene】\n"
                + json.dumps(scene_payload, ensure_ascii=False)
            ),
            schema=_extract_schema(),
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            temperature=0.1,
            metadata={"scene_id": scene.id, "chapter_id": chapter.id},
        )
    except Exception:  # noqa: BLE001
        _logger.warning("extract_temporal_state_failed", exc_info=True)
        return {"updated": False, "error": "model_failed"}

    if not isinstance(raw, dict):
        return {"updated": False, "error": "invalid_response"}
    try:
        offset = int(raw.get("in_story_day_offset"))
        tod = str(raw.get("time_of_day") or "").lower().strip()
        duration = int(raw.get("duration_minutes"))
    except (TypeError, ValueError):
        return {"updated": False, "error": "bad_types"}

    if tod not in _ALLOWED_TIME_OF_DAY:
        # 模型偶尔吐中文/同义词，尝试归一
        cn_map = {
            "凌晨": "dawn",
            "清晨": "morning",
            "早晨": "morning",
            "上午": "morning",
            "中午": "noon",
            "下午": "afternoon",
            "傍晚": "dusk",
            "黄昏": "dusk",
            "晚上": "night",
            "夜晚": "night",
            "深夜": "night",
        }
        tod = cn_map.get(tod, "")
        if not tod:
            return {"updated": False, "error": "bad_time_of_day"}

    if offset < 0:
        offset = 0
    if duration < 0:
        duration = 0

    # 防止 LLM 让时间倒退超过 1 天（与 audit 规则呼应；偶发 1 天内倒退保留，
    # 比如同一日上午 → 凌晨这种异常已经够罕见）
    if previous and offset < (previous["in_story_day_offset"] or 0) - 1:
        offset = previous["in_story_day_offset"]

    scene.in_story_day_offset = offset
    scene.time_of_day = tod
    scene.duration_minutes = duration
    await session.flush()
    return {
        "updated": True,
        "in_story_day_offset": offset,
        "time_of_day": tod,
        "duration_minutes": duration,
    }


__all__ = ["extract_temporal_state_from_scene"]
