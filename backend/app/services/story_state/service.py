from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.scene import Scene
from app.models.story_state_item import StoryStateItem
from app.repositories import (
    ChapterStateRequirementRepository,
    StoryStateHistoryRepository,
    StoryStateRepository,
)


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class StoryStateInput:
    entity_type: str
    entity_id: str | None
    state_type: str
    name: str
    summary: str = ""
    status: str = "active"
    value_json: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    is_hard_constraint: bool = False
    source_excerpt: str = ""
    requirement_hint: str = ""
    requirement_type: str = "must_remember"


class StoryStateService:
    async def upsert_state_item(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str | None,
        scene_id: str | None,
        created_by: str | None,
        state_input: StoryStateInput,
        change_type: str = "update",
    ) -> tuple[StoryStateItem, bool]:
        state_repo = StoryStateRepository(session)
        history_repo = StoryStateHistoryRepository(session)
        existing = await state_repo.get_by_identity(
            organization_id=organization_id,
            project_id=project_id,
            entity_type=state_input.entity_type,
            entity_id=state_input.entity_id,
            state_type=state_input.state_type,
            name=state_input.name,
        )
        clean_summary = _normalized_text(state_input.summary)
        clean_excerpt = _normalized_text(state_input.source_excerpt)
        clean_value = _json_dict(state_input.value_json)
        if existing is None:
            created = await state_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                entity_type=state_input.entity_type,
                entity_id=state_input.entity_id,
                state_type=state_input.state_type,
                name=state_input.name,
                status=_normalized_text(state_input.status) or "active",
                summary=clean_summary,
                value_json=clean_value,
                source_chapter_id=chapter_id,
                source_scene_id=scene_id,
                source_excerpt=clean_excerpt,
                updated_in_chapter_id=chapter_id,
                priority=max(0, int(state_input.priority or 0)),
                is_hard_constraint=bool(state_input.is_hard_constraint),
            )
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=created.id,
                chapter_id=chapter_id,
                scene_id=scene_id,
                change_type="create",
                before_json={},
                after_json=self.snapshot(created),
                reason="story_state_extracted",
                source_excerpt=clean_excerpt,
                created_by=created_by,
            )
            return created, True

        before = self.snapshot(existing)
        changed = False
        if clean_summary and clean_summary != _normalized_text(existing.summary):
            existing.summary = clean_summary
            changed = True
        if clean_value and clean_value != _json_dict(existing.value_json):
            existing.value_json = clean_value
            changed = True
        status = _normalized_text(state_input.status) or existing.status
        if status != existing.status:
            existing.status = status
            changed = True
        priority = max(0, int(state_input.priority or 0))
        if priority != int(existing.priority or 0):
            existing.priority = priority
            changed = True
        hard = bool(state_input.is_hard_constraint)
        if hard != bool(existing.is_hard_constraint):
            existing.is_hard_constraint = hard
            changed = True
        if scene_id and existing.source_scene_id != scene_id:
            existing.source_scene_id = scene_id
            changed = True
        if chapter_id and existing.updated_in_chapter_id != chapter_id:
            existing.updated_in_chapter_id = chapter_id
            changed = True
        if chapter_id and not existing.source_chapter_id:
            existing.source_chapter_id = chapter_id
            changed = True
        if clean_excerpt and clean_excerpt != _normalized_text(existing.source_excerpt):
            existing.source_excerpt = clean_excerpt
            changed = True
        if changed:
            existing.updated_at = _now()
            await session.flush()
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=existing.id,
                chapter_id=chapter_id,
                scene_id=scene_id,
                change_type=change_type,
                before_json=before,
                after_json=self.snapshot(existing),
                reason="story_state_extracted",
                source_excerpt=clean_excerpt or existing.source_excerpt,
                created_by=created_by,
            )
        return existing, changed

    async def rebuild_chapter_requirements(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene | None,
        state_inputs: Sequence[StoryStateInput],
    ) -> dict[str, int]:
        req_repo = ChapterStateRequirementRepository(session)
        deleted = await req_repo.delete_for_chapter(
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
        )
        created = 0
        state_repo = StoryStateRepository(session)
        dedupe_keys: set[tuple[str, str, str]] = set()
        for item in state_inputs:
            if not item.requirement_hint.strip():
                continue
            state = await state_repo.get_by_identity(
                organization_id=organization_id,
                project_id=project_id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                state_type=item.state_type,
                name=item.name,
            )
            if not state:
                continue
            dedupe_key = (state.id, item.requirement_type, item.requirement_hint.strip())
            if dedupe_key in dedupe_keys:
                continue
            dedupe_keys.add(dedupe_key)
            await req_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter.id,
                state_item_id=state.id,
                requirement_type=item.requirement_type or "must_remember",
                summary=item.requirement_hint.strip(),
                priority=max(0, int(item.priority or 0)),
            )
            created += 1
        return {
            "deleted": deleted,
            "created": created,
            "chapter_id": chapter.id,
            "scene_id": scene.id if scene else None,
        }

    def snapshot(self, state: StoryStateItem) -> dict[str, Any]:
        return {
            "entity_type": state.entity_type,
            "entity_id": state.entity_id,
            "state_type": state.state_type,
            "name": state.name,
            "status": state.status,
            "summary": state.summary,
            "value_json": dict(state.value_json or {}),
            "source_chapter_id": state.source_chapter_id,
            "source_scene_id": state.source_scene_id,
            "source_excerpt": state.source_excerpt,
            "updated_in_chapter_id": state.updated_in_chapter_id,
            "priority": state.priority,
            "is_hard_constraint": state.is_hard_constraint,
        }


story_state_service = StoryStateService()
