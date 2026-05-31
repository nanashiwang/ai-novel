"""关键状态 API（第一阶段底座）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.models.chapter import Chapter
from app.models.chapter_state_requirement import ChapterStateRequirement
from app.models.continuity_issue import ContinuityIssue
from app.models.story_state_item import StoryStateItem
from app.repositories import (
    ChapterRepository,
    ChapterStateRequirementRepository,
    ProjectRepository,
    StoryStateHistoryRepository,
    StoryStateRepository,
)
from app.schemas.story_state import (
    ChapterStateRequirementCreateRequest,
    ChapterStateRequirementListResponse,
    ChapterStateRequirementPatchRequest,
    ChapterStateRequirementResponse,
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


async def _get_chapter_or_404(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> Chapter:
    chapter = await ChapterRepository(db).get(
        chapter_id,
        organization_id=tenant.organization_id,
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    return chapter


async def _get_requirement_or_404(
    project_id: str,
    chapter_id: str,
    requirement_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> ChapterStateRequirement:
    requirement = await ChapterStateRequirementRepository(db).get(
        requirement_id,
        organization_id=tenant.organization_id,
    )
    if (
        not requirement
        or requirement.project_id != project_id
        or requirement.chapter_id != chapter_id
    ):
        raise NotFoundError("chapter_state_requirement_not_found")
    return requirement


async def _get_source_issue_or_404(
    project_id: str,
    issue_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> ContinuityIssue:
    result = await db.execute(
        select(ContinuityIssue).where(
            ContinuityIssue.organization_id == tenant.organization_id,
            ContinuityIssue.project_id == project_id,
            ContinuityIssue.id == issue_id,
        )
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("continuity_issue_not_found")
    return issue


async def _build_requirement_responses(
    *,
    project_id: str,
    tenant: TenantDep,
    db: DbDep,
    items: list[ChapterStateRequirement],
) -> list[dict[str, Any]]:
    state_ids = {item.state_item_id for item in items}
    source_chapter_ids = {
        item.source_chapter_id
        for item in items
        if item.source_chapter_id
    }
    state_by_id: dict[str, StoryStateItem] = {}
    if state_ids:
        result = await db.execute(
            select(StoryStateItem).where(
                StoryStateItem.organization_id == tenant.organization_id,
                StoryStateItem.project_id == project_id,
                StoryStateItem.id.in_(state_ids),
            )
        )
        state_by_id = {state.id: state for state in result.scalars().all()}
    source_chapter_by_id: dict[str, Chapter] = {}
    if source_chapter_ids:
        result = await db.execute(
            select(Chapter).where(
                Chapter.organization_id == tenant.organization_id,
                Chapter.project_id == project_id,
                Chapter.id.in_(source_chapter_ids),
            )
        )
        source_chapter_by_id = {row.id: row for row in result.scalars().all()}
    return [
        {
            "id": item.id,
            "state_item_id": item.state_item_id,
            "requirement_type": item.requirement_type,
            "summary": item.summary,
            "priority": item.priority,
            "origin_type": item.origin_type or "current_chapter_extract",
            "status": item.status or "active",
            "superseded_by_requirement_id": item.superseded_by_requirement_id,
            "source_issue_id": item.source_issue_id,
            "status_reason": item.status_reason or "",
            "source_chapter_id": item.source_chapter_id,
            "source_chapter_index": (
                source_chapter_by_id[item.source_chapter_id].chapter_index
                if item.source_chapter_id in source_chapter_by_id
                else None
            ),
            "source_chapter_title": (
                source_chapter_by_id[item.source_chapter_id].title
                if item.source_chapter_id in source_chapter_by_id
                else None
            ),
            "source_scene_id": item.source_scene_id,
            "target_chapter_id": item.target_chapter_id or item.chapter_id,
            "state_item": state_by_id.get(item.state_item_id),
        }
        for item in items
    ]


async def _build_requirement_response(
    *,
    project_id: str,
    tenant: TenantDep,
    db: DbDep,
    item: ChapterStateRequirement,
) -> dict[str, Any]:
    responses = await _build_requirement_responses(
        project_id=project_id,
        tenant=tenant,
        db=db,
        items=[item],
    )
    return responses[0]


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
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    items = await ChapterStateRequirementRepository(db).list_for_chapter(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return ChapterStateRequirementListResponse(
        items=await _build_requirement_responses(
            project_id=project_id,
            tenant=tenant,
            db=db,
            items=list(items),
        ),
    )


@chapter_router.post(
    "/{chapter_id}/state-requirements",
    response_model=ChapterStateRequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chapter_state_requirement(
    project_id: str,
    chapter_id: str,
    payload: ChapterStateRequirementCreateRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    state = await _get_story_state_or_404(project_id, payload.state_item_id, tenant, db)
    source_issue_id = (payload.source_issue_id or "").strip() or None
    if source_issue_id:
        await _get_source_issue_or_404(project_id, source_issue_id, tenant, db)
    requirement = await ChapterStateRequirementRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
        state_item_id=state.id,
        requirement_type=payload.requirement_type,
        summary=payload.summary.strip() or state.summary,
        priority=max(0, int(payload.priority or 0)),
        origin_type="manual",
        status="active",
        source_issue_id=source_issue_id,
        source_chapter_id=None,
        source_scene_id=None,
        target_chapter_id=chapter_id,
    )
    await db.commit()
    return await _build_requirement_response(
        project_id=project_id,
        tenant=tenant,
        db=db,
        item=requirement,
    )


@chapter_router.patch(
    "/{chapter_id}/state-requirements/{requirement_id}",
    response_model=ChapterStateRequirementResponse,
)
async def patch_chapter_state_requirement(
    project_id: str,
    chapter_id: str,
    requirement_id: str,
    payload: ChapterStateRequirementPatchRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    requirement = await _get_requirement_or_404(
        project_id,
        chapter_id,
        requirement_id,
        tenant,
        db,
    )
    updates = payload.model_dump(exclude_none=True)
    if "summary" in updates:
        updates["summary"] = str(updates["summary"]).strip()
    if "status_reason" in updates:
        updates["status_reason"] = str(updates["status_reason"]).strip()
    if "superseded_by_requirement_id" in updates and not updates["superseded_by_requirement_id"]:
        updates["superseded_by_requirement_id"] = None
    if "priority" in updates:
        updates["priority"] = max(0, int(updates["priority"] or 0))
    updates["origin_type"] = "manual"
    updated = await ChapterStateRequirementRepository(db).update(
        requirement.id,
        updates,
        organization_id=tenant.organization_id,
    )
    if not updated:
        raise NotFoundError("chapter_state_requirement_not_found")
    await db.commit()
    return await _build_requirement_response(
        project_id=project_id,
        tenant=tenant,
        db=db,
        item=updated,
    )


@chapter_router.delete(
    "/{chapter_id}/state-requirements/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chapter_state_requirement(
    project_id: str,
    chapter_id: str,
    requirement_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    requirement = await _get_requirement_or_404(
        project_id,
        chapter_id,
        requirement_id,
        tenant,
        db,
    )
    await ChapterStateRequirementRepository(db).delete(
        requirement.id,
        organization_id=tenant.organization_id,
    )
    await db.commit()
