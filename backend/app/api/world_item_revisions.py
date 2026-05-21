"""世界观条目 revision API。

Sprint 12-C：镜像 character_revisions 模式。提供 list / apply / reject /
rollback + pending-count 端点，让前端能审核 AI 推演 + copilot 提案。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import (
    WorldItemRepository,
    WorldItemRevisionRepository,
)
from app.schemas.common import APIModel
from app.services import world_tracker

router = APIRouter(
    prefix="/projects/{project_id}/world-items",
    tags=["world-item-revisions"],
)


class WorldItemRevisionResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    item_id: str
    field: str
    old_value: Any | None = None
    new_value: Any | None = None
    reason: str = ""
    source: str
    scene_id: str | None = None
    status: str
    created_by: str | None = None
    applied_by: str | None = None
    applied_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PendingCountResponse(APIModel):
    total: int = 0
    by_item: dict[str, int] = Field(default_factory=dict)


@router.get("/pending-count", response_model=PendingCountResponse)
async def world_item_pending_count(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    total = await world_tracker.count_pending_for_project(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    by_item = await world_tracker.count_pending_by_item(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    return PendingCountResponse(total=total, by_item=by_item)


@router.get(
    "/{item_id}/revisions",
    response_model=list[WorldItemRevisionResponse],
)
async def list_world_item_revisions(
    project_id: str,
    item_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    status: str | None = None,
):
    require_permission(user, "project:read", tenant)
    item = await WorldItemRepository(db).get(item_id, organization_id=tenant.organization_id)
    if not item or item.project_id != project_id:
        raise NotFoundError("world_item_not_found", code="world_item_not_found")
    return await world_tracker.list_revisions(
        db,
        organization_id=tenant.organization_id,
        item_id=item.id,
        status=status,
    )


@router.post(
    "/{item_id}/revisions/{revision_id}/apply",
    response_model=WorldItemRevisionResponse,
)
async def apply_world_item_revision(
    project_id: str,
    item_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    revision = await WorldItemRevisionRepository(db).get(
        revision_id, organization_id=tenant.organization_id
    )
    if not revision or revision.item_id != item_id or revision.project_id != project_id:
        raise NotFoundError(
            "world_item_revision_not_found", code="world_item_revision_not_found"
        )
    item = await world_tracker.apply_revision(
        db,
        organization_id=tenant.organization_id,
        revision=revision,
        user_id=user.id,
    )
    if item is None:
        raise NotFoundError(
            "world_item_revision_not_found", code="world_item_revision_not_found"
        )
    await db.commit()
    return revision


@router.post(
    "/{item_id}/revisions/{revision_id}/reject",
    response_model=WorldItemRevisionResponse,
)
async def reject_world_item_revision(
    project_id: str,
    item_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    revision = await WorldItemRevisionRepository(db).get(
        revision_id, organization_id=tenant.organization_id
    )
    if not revision or revision.item_id != item_id or revision.project_id != project_id:
        raise NotFoundError(
            "world_item_revision_not_found", code="world_item_revision_not_found"
        )
    result = await world_tracker.reject_revision(
        db,
        revision=revision,
        user_id=user.id,
    )
    if result is None:
        raise NotFoundError(
            "world_item_revision_not_found", code="world_item_revision_not_found"
        )
    await db.commit()
    return revision


@router.post(
    "/{item_id}/revisions/{revision_id}/rollback",
    response_model=WorldItemRevisionResponse,
)
async def rollback_world_item_revision(
    project_id: str,
    item_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    revision = await WorldItemRevisionRepository(db).get(
        revision_id, organization_id=tenant.organization_id
    )
    if not revision or revision.item_id != item_id or revision.project_id != project_id:
        raise NotFoundError(
            "world_item_revision_not_found", code="world_item_revision_not_found"
        )
    item = await world_tracker.rollback_to(
        db,
        organization_id=tenant.organization_id,
        revision=revision,
        user_id=user.id,
    )
    if item is None:
        raise NotFoundError(
            "world_item_revision_not_found", code="world_item_revision_not_found"
        )
    await db.commit()
    return revision
