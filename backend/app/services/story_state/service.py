from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.chapter_state_requirement import ChapterStateRequirement
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


_NEXT_CHAPTER_REQUIREMENT_MARKERS = (
    "下一章",
    "下章",
    "下个章节",
    "后续章节",
    "后文",
    "此后",
    "之后",
    "日后",
    "往后",
    "以后",
    "后续",
)


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
        deleted = await self._delete_rebuildable_requirements(
            req_repo,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
        )
        state_repo = StoryStateRepository(session)
        requirement_items: list[tuple[StoryStateInput, StoryStateItem, str]] = []
        dedupe_keys: set[tuple[str, str, str]] = set()
        for item in state_inputs:
            summary = item.requirement_hint.strip()
            if not summary:
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
            dedupe_key = (state.id, item.requirement_type, summary)
            if dedupe_key in dedupe_keys:
                continue
            dedupe_keys.add(dedupe_key)
            requirement_items.append((item, state, summary))

        created, updated = await self._upsert_requirements_for_chapter(
            req_repo,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
            source_chapter_id=chapter.id,
            source_scene_id=scene.id if scene else None,
            target_chapter_id=chapter.id,
            origin_type="current_chapter_extract",
            requirement_items=requirement_items,
        )
        next_items = [
            item
            for item in requirement_items
            if _is_next_chapter_requirement(item[2])
        ]
        next_chapter = (
            await self._find_next_chapter(
                session,
                organization_id=organization_id,
                project_id=project_id,
                chapter=chapter,
            )
            if next_items
            else None
        )
        next_created = 0
        next_updated = 0
        if next_chapter is not None:
            next_created, next_updated = await self._upsert_requirements_for_chapter(
                req_repo,
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=next_chapter.id,
                source_chapter_id=chapter.id,
                source_scene_id=scene.id if scene else None,
                target_chapter_id=next_chapter.id,
                origin_type="previous_chapter_carryover",
                requirement_items=next_items,
            )
        return {
            "deleted": deleted,
            "created": created,
            "updated": updated,
            "next_chapter_created": next_created,
            "next_chapter_updated": next_updated,
            "next_chapter_id": next_chapter.id if next_chapter else None,
            "chapter_id": chapter.id,
            "scene_id": scene.id if scene else None,
        }

    async def _delete_rebuildable_requirements(
        self,
        req_repo: ChapterStateRequirementRepository,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
    ) -> int:
        """重建当前章要求时，保留从前文传播来的未来向承接要求。"""
        existing = list(
            await req_repo.list_for_chapter(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter_id,
            )
        )
        deleted = 0
        for row in existing:
            if _is_preserved_requirement(row):
                continue
            await req_repo.session.delete(row)
            deleted += 1
        if deleted:
            await req_repo.session.flush()
        return deleted

    async def _upsert_requirements_for_chapter(
        self,
        req_repo: ChapterStateRequirementRepository,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
        source_chapter_id: str | None,
        source_scene_id: str | None,
        target_chapter_id: str | None,
        origin_type: str,
        requirement_items: Sequence[tuple[StoryStateInput, StoryStateItem, str]],
    ) -> tuple[int, int]:
        existing = list(
            await req_repo.list_for_chapter(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter_id,
            )
        )
        existing_by_key = {
            (row.state_item_id, row.requirement_type, row.summary.strip()): row
            for row in existing
        }
        created = 0
        updated = 0
        for item, state, summary in requirement_items:
            requirement_type = item.requirement_type or "must_remember"
            priority = max(0, int(item.priority or 0))
            key = (state.id, requirement_type, summary)
            current = existing_by_key.get(key)
            if current is not None:
                if int(current.priority or 0) < priority:
                    current.priority = priority
                    updated += 1
                if _apply_requirement_source(
                    current,
                    source_chapter_id=source_chapter_id,
                    source_scene_id=source_scene_id,
                    target_chapter_id=target_chapter_id,
                    origin_type=origin_type,
                ):
                    updated += 1
                continue
            created_row = await req_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter_id,
                source_chapter_id=source_chapter_id,
                source_scene_id=source_scene_id,
                target_chapter_id=target_chapter_id or chapter_id,
                origin_type=origin_type,
                state_item_id=state.id,
                requirement_type=requirement_type,
                summary=summary,
                priority=priority,
            )
            existing_by_key[key] = created_row
            created += 1
        if updated:
            await req_repo.session.flush()
        return created, updated

    async def _find_next_chapter(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
    ) -> Chapter | None:
        result = await session.execute(
            select(Chapter).where(
                Chapter.organization_id == organization_id,
                Chapter.project_id == project_id,
                Chapter.chapter_index == int(chapter.chapter_index or 0) + 1,
            )
        )
        return result.scalar_one_or_none()

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


def _is_next_chapter_requirement(summary: str) -> bool:
    text = (summary or "").strip()
    if not text or text.startswith("本章后续"):
        return False
    return any(marker in text for marker in _NEXT_CHAPTER_REQUIREMENT_MARKERS)


def _is_preserved_requirement(row: ChapterStateRequirement) -> bool:
    origin_type = (row.origin_type or "").strip()
    if origin_type in {"previous_chapter_carryover", "manual"}:
        return True
    # Backward compatibility for rows created before origin_type existed.
    return _is_next_chapter_requirement(row.summary or "")


def _apply_requirement_source(
    row: ChapterStateRequirement,
    *,
    source_chapter_id: str | None,
    source_scene_id: str | None,
    target_chapter_id: str | None,
    origin_type: str,
) -> bool:
    changed = False
    if not row.source_chapter_id and source_chapter_id:
        row.source_chapter_id = source_chapter_id
        changed = True
    if not row.source_scene_id and source_scene_id:
        row.source_scene_id = source_scene_id
        changed = True
    if not row.target_chapter_id and target_chapter_id:
        row.target_chapter_id = target_chapter_id
        changed = True
    current_origin = (row.origin_type or "").strip()
    if (
        origin_type == "previous_chapter_carryover"
        and current_origin != "previous_chapter_carryover"
    ) or not current_origin:
        row.origin_type = origin_type
        changed = True
    return changed
