"""关键状态 API（第一阶段底座）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.models.story_state_item import StoryStateItem
from app.repositories import (
    ChapterRepository,
    ChapterStateRequirementRepository,
    ProjectRepository,
    StoryStateHistoryRepository,
    StoryStateRepository,
)
from app.schemas.story_state import (
    ChapterStateRequirementListResponse,
    StoryStateHistoryListResponse,
    StoryStateItemResponse,
    StoryStateListResponse,
    StoryStatePatchRequest,
)

router = APIRouter(prefix="/projects/{project_id}/story-states", tags=["story-states"])
chapter_router = APIRouter(prefix="/projects/{project_id}/chapters", tags=["story-states"])


async def _get_project_or_404(project_id: str, tenant: TenantDep, db: DbDep):
    project = await ProjectRepository(db).get(
        project_id,
        organization_id=tenant.organization_id,
    )
    if not project:
        raise NotFoundError("project_not_found")
    return project


async def _get_story_state_or_404(
    project_id: str,
    state_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> StoryStateItem:
    state = await StoryStateRepository(db).get(
        state_id,
        organization_id=tenant.organization_id,
    )
    if not state or state.project_id != project_id:
        raise NotFoundError("story_state_not_found")
    return state


def _state_snapshot(state: StoryStateItem) -> dict[str, Any]:
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


@router.get("", response_model=StoryStateListResponse)
async def list_story_states(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    state_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    hard_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    items = await StoryStateRepository(db).list_filtered(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_type=state_type,
        status=status,
        entity_type=entity_type,
        hard_only=hard_only,
        limit=limit,
    )
    return StoryStateListResponse(items=list(items))


@router.get("/{state_id}", response_model=StoryStateItemResponse)
async def get_story_state(
    project_id: str,
    state_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    return await _get_story_state_or_404(project_id, state_id, tenant, db)


@router.get("/{state_id}/history", response_model=StoryStateHistoryListResponse)
async def get_story_state_history(
    project_id: str,
    state_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_story_state_or_404(project_id, state_id, tenant, db)
    items = await StoryStateHistoryRepository(db).list_for_state(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_item_id=state_id,
    )
    return StoryStateHistoryListResponse(items=list(items))


@router.patch("/{state_id}", response_model=StoryStateItemResponse)
async def patch_story_state(
    project_id: str,
    state_id: str,
    payload: StoryStatePatchRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    state = await _get_story_state_or_404(project_id, state_id, tenant, db)
    before = _state_snapshot(state)
    updates = payload.model_dump(exclude_none=True, exclude={"reason"})
    updated = await StoryStateRepository(db).update(
        state_id,
        updates,
        organization_id=tenant.organization_id,
    )
    if not updated:
        raise NotFoundError("story_state_not_found")
    await StoryStateHistoryRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_item_id=state_id,
        chapter_id=updated.updated_in_chapter_id,
        scene_id=updated.source_scene_id,
        change_type="update",
        before_json=before,
        after_json=_state_snapshot(updated),
        reason=payload.reason or "manual_update_story_state",
        source_excerpt=updated.source_excerpt,
        created_by=user.id,
    )
    await db.commit()
    return updated


@chapter_router.get(
    "/{chapter_id}/state-requirements",
    response_model=ChapterStateRequirementListResponse,
)
async def list_chapter_state_requirements(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    chapter = await ChapterRepository(db).get(
        chapter_id,
        organization_id=tenant.organization_id,
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    items = await ChapterStateRequirementRepository(db).list_for_chapter(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return ChapterStateRequirementListResponse(items=list(items))
