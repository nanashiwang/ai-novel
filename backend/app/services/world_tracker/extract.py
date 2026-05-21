"""从 scene 正文反推 world_item 字段变化，写 pending revision。

Sprint 12-C：在 write_scene / rewrite_scene 完成后由 activity 异步调用。
失败 swallow + warn，绝不阻塞主流程。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.scene import Scene
from app.repositories import WorldItemRepository
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.world_tracker import (
    WORLD_ITEM_TRACKABLE_FIELDS,
    record_ai_inferred,
)

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "world/extract_changes"
_PROMPT_VERSION = "v1"


def _extract_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "field": {"type": "string"},
                        "new_value": {},
                        "reason": {"type": "string"},
                    },
                    "required": ["item_id", "field", "new_value"],
                },
            }
        },
        "required": ["changes"],
    }


async def extract_world_changes_from_scene(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    job_id: str | None,
    chapter: Chapter,
    scene: Scene,
    draft: DraftVersion,
) -> dict[str, int]:
    """从 draft 正文反推 world_items 字段变化，写 pending revision。

    返回 {"pending_count": N, "considered_count": M}；失败时记 warn 并返回
    {"pending_count": 0, "considered_count": 0, "error": "..."}。
    """
    items = list(
        await WorldItemRepository(session).list(
            organization_id=organization_id,
            project_id=project_id,
            limit=80,
        )
    )
    if not items:
        return {"pending_count": 0, "considered_count": 0, "skipped": True}

    snapshot = [
        {
            "id": item.id,
            "type": item.type,
            "name": item.name,
            "description": item.description,
            "importance": item.importance,
            "is_hard_rule": bool(item.is_hard_rule),
        }
        for item in items
    ]
    scene_payload = {
        "chapter_index": chapter.chapter_index,
        "chapter_title": chapter.title,
        "scene_index": scene.scene_index,
        "scene_title": scene.title,
        "location": scene.location,
        "characters": scene.characters or [],
        "goal": scene.goal,
        "conflict": scene.conflict,
        "reveal": scene.reveal,
        "draft_excerpt": (draft.content or "")[:6000],
    }
    try:
        prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="extract_world_changes",
            system_prompt=prompt
            or "你是世界观追踪助手，请基于 scene 正文输出 JSON。",
            user_prompt=(
                "【已有世界观条目】\n"
                + json.dumps(snapshot, ensure_ascii=False)
                + "\n\n【当前 scene】\n"
                + json.dumps(scene_payload, ensure_ascii=False)
            ),
            schema=_extract_schema(),
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            temperature=0.2,
            metadata={"scene_id": scene.id, "chapter_id": chapter.id},
        )
    except Exception:  # noqa: BLE001
        _logger.warning("extract_world_changes_failed", exc_info=True)
        return {"pending_count": 0, "considered_count": 0, "error": "model_failed"}

    by_id = {item.id: item for item in items}
    pending_count = 0
    considered_count = 0
    for entry in (raw or {}).get("changes") or []:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id") or "")
        field = str(entry.get("field") or "")
        new_value = entry.get("new_value")
        reason = str(entry.get("reason") or "AI 推演")
        if field not in WORLD_ITEM_TRACKABLE_FIELDS:
            continue
        item = by_id.get(item_id)
        if not item:
            continue
        considered_count += 1
        rev = await record_ai_inferred(
            session,
            organization_id=organization_id,
            project_id=project_id,
            item=item,
            field=field,
            new_value=new_value,
            reason=reason,
            scene_id=scene.id,
        )
        if rev is not None:
            pending_count += 1
    return {
        "pending_count": pending_count,
        "considered_count": considered_count,
    }
