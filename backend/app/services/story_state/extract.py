"""从 scene 正文提取关键状态项，并重建章节承接 requirement。"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.scene import Scene
from app.repositories import StoryStateRepository
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.story_state.service import StoryStateInput, story_state_service

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "story_state/extract_changes"
_PROMPT_VERSION = "v1"

_ALLOWED_ENTITY_TYPES = {
    "character",
    "artifact",
    "plot_thread",
    "relationship",
    "world_rule",
}
_ALLOWED_STATE_TYPES = {
    "skill",
    "artifact",
    "identity",
    "grudge",
    "foreshadow",
    "oath",
}
_ALLOWED_REQUIREMENT_TYPES = {
    "must_remember",
    "must_not_conflict",
    "should_reference",
    "candidate_payoff",
}


def _extract_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "enum": sorted(_ALLOWED_ENTITY_TYPES)},
                        "entity_id": {"type": ["string", "null"]},
                        "state_type": {"type": "string", "enum": sorted(_ALLOWED_STATE_TYPES)},
                        "name": {"type": "string"},
                        "summary": {"type": "string"},
                        "status": {"type": "string"},
                        "value_json": {"type": "object"},
                        "priority": {"type": "integer"},
                        "is_hard_constraint": {"type": "boolean"},
                        "source_excerpt": {"type": "string"},
                        "requirement_type": {
                            "type": "string",
                            "enum": sorted(_ALLOWED_REQUIREMENT_TYPES),
                        },
                        "requirement_hint": {"type": "string"},
                    },
                    "required": ["entity_type", "state_type", "name"],
                },
            }
        },
        "required": ["items"],
    }


def _scene_payload(chapter: Chapter, scene: Scene, draft: DraftVersion) -> dict[str, Any]:
    return {
        "chapter_index": chapter.chapter_index,
        "chapter_title": chapter.title,
        "chapter_summary": chapter.summary,
        "chapter_goal": chapter.goal,
        "scene_index": scene.scene_index,
        "scene_title": scene.title,
        "location": scene.location,
        "characters": scene.characters or [],
        "scene_purpose": scene.scene_purpose,
        "entry_state": scene.entry_state,
        "exit_state": scene.exit_state,
        "goal": scene.goal,
        "conflict": scene.conflict,
        "reveal": scene.reveal,
        "hook": scene.hook,
        "draft_excerpt": (draft.content or "")[:7000],
    }


async def extract_story_state_from_scene(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    job_id: str | None,
    chapter: Chapter,
    scene: Scene,
    draft: DraftVersion,
    created_by: str | None,
) -> dict[str, Any]:
    if not draft or not draft.content.strip():
        return {"upserted_count": 0, "requirement_count": 0, "skipped": "no_draft"}

    existing = list(
        await StoryStateRepository(session).list_filtered(
            organization_id=organization_id,
            project_id=project_id,
            limit=120,
        )
    )
    snapshot = [
        {
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "state_type": item.state_type,
            "name": item.name,
            "status": item.status,
            "summary": item.summary,
            "value_json": dict(item.value_json or {}),
            "priority": item.priority,
            "is_hard_constraint": bool(item.is_hard_constraint),
        }
        for item in existing
    ]
    try:
        prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="extract_story_state",
            system_prompt=prompt
            or "你是小说关键设定追踪助手，请基于正文提取需要长期记忆的状态项。",
            user_prompt=(
                "【已有关键状态项】\n"
                + json.dumps(snapshot, ensure_ascii=False)
                + "\n\n【当前 scene】\n"
                + json.dumps(_scene_payload(chapter, scene, draft), ensure_ascii=False)
            ),
            schema=_extract_schema(),
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            temperature=0.2,
            metadata={"scene_id": scene.id, "chapter_id": chapter.id},
        )
    except Exception:  # noqa: BLE001
        _logger.warning("extract_story_state_failed", exc_info=True)
        return {"upserted_count": 0, "requirement_count": 0, "error": "model_failed"}

    items = (raw or {}).get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return {"upserted_count": 0, "requirement_count": 0, "error": "invalid_response"}

    parsed: list[StoryStateInput] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        entity_type = str(entry.get("entity_type") or "").strip()
        state_type = str(entry.get("state_type") or "").strip()
        name = str(entry.get("name") or "").strip()
        if entity_type not in _ALLOWED_ENTITY_TYPES or state_type not in _ALLOWED_STATE_TYPES:
            continue
        if not name:
            continue
        requirement_type = str(entry.get("requirement_type") or "must_remember").strip()
        if requirement_type not in _ALLOWED_REQUIREMENT_TYPES:
            requirement_type = "must_remember"
        parsed.append(
            StoryStateInput(
                entity_type=entity_type,
                entity_id=(str(entry.get("entity_id")).strip() if entry.get("entity_id") else None),
                state_type=state_type,
                name=name,
                summary=str(entry.get("summary") or "").strip(),
                status=str(entry.get("status") or "active").strip() or "active",
                value_json=(
                    entry.get("value_json")
                    if isinstance(entry.get("value_json"), dict)
                    else {}
                ),
                priority=max(0, int(entry.get("priority") or 0)),
                is_hard_constraint=bool(entry.get("is_hard_constraint")),
                source_excerpt=str(entry.get("source_excerpt") or "").strip(),
                requirement_type=requirement_type,
                requirement_hint=str(entry.get("requirement_hint") or "").strip(),
            )
        )

    upserted = 0
    changed = 0
    for item in parsed:
        _, did_change = await story_state_service.upsert_state_item(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            created_by=created_by,
            state_input=item,
            change_type="update",
        )
        upserted += 1
        if did_change:
            changed += 1

    requirement_result = await story_state_service.rebuild_chapter_requirements(
        session,
        organization_id=organization_id,
        project_id=project_id,
        chapter=chapter,
        scene=scene,
        state_inputs=parsed,
    )
    return {
        "upserted_count": upserted,
        "changed_count": changed,
        "requirement_count": requirement_result["created"],
        "requirement_deleted": requirement_result["deleted"],
        "requirement_next_chapter_count": requirement_result.get(
            "next_chapter_created", 0
        ),
        "requirement_next_chapter_updated": requirement_result.get(
            "next_chapter_updated", 0
        ),
        "requirement_next_chapter_id": requirement_result.get("next_chapter_id"),
    }


__all__ = ["extract_story_state_from_scene"]
