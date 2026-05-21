"""剧情线 revision API。

Sprint 12-C：与 world_item_revisions 完全对称的端点集合。
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
    PlotThreadRepository,
    PlotThreadRevisionRepository,
)
from app.schemas.common import APIModel
from app.services import plot_thread_tracker

router = APIRouter(
    prefix="/projects/{project_id}/plot-threads",
    tags=["plot-thread-revisions"],
)


class PlotThreadRevisionResponse(APIModel):
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
async def plot_thread_pending_count(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    total = await plot_thread_tracker.count_pending_for_project(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    by_item = await plot_thread_tracker.count_pending_by_item(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    return PendingCountResponse(total=total, by_item=by_item)


@router.get(
    "/{thread_id}/revisions",
    response_model=list[PlotThreadRevisionResponse],
)
async def list_plot_thread_revisions(
    project_id: str,
    thread_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    status: str | None = None,
):
    require_permission(user, "project:read", tenant)
    item = await PlotThreadRepository(db).get(
        thread_id, organization_id=tenant.organization_id
    )
    if not item or item.project_id != project_id:
        raise NotFoundError("plot_thread_not_found", code="plot_thread_not_found")
    return await plot_thread_tracker.list_revisions(
        db,
        organization_id=tenant.organization_id,
        item_id=item.id,
        status=status,
    )


@router.post(
    "/{thread_id}/revisions/{revision_id}/apply",
    response_model=PlotThreadRevisionResponse,
)
async def apply_plot_thread_revision(
    project_id: str,
    thread_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    revision = await PlotThreadRevisionRepository(db).get(
        revision_id, organization_id=tenant.organization_id
    )
    if not revision or revision.item_id != thread_id or revision.project_id != project_id:
        raise NotFoundError(
            "plot_thread_revision_not_found", code="plot_thread_revision_not_found"
        )
    item = await plot_thread_tracker.apply_revision(
        db,
        organization_id=tenant.organization_id,
        revision=revision,
        user_id=user.id,
    )
    if item is None:
        raise NotFoundError(
            "plot_thread_revision_not_found", code="plot_thread_revision_not_found"
        )
    await db.flush()
    await db.refresh(revision)
    await db.commit()
    return revision


@router.post(
    "/{thread_id}/revisions/{revision_id}/reject",
    response_model=PlotThreadRevisionResponse,
)
async def reject_plot_thread_revision(
    project_id: str,
    thread_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    revision = await PlotThreadRevisionRepository(db).get(
        revision_id, organization_id=tenant.organization_id
    )
    if not revision or revision.item_id != thread_id or revision.project_id != project_id:
        raise NotFoundError(
            "plot_thread_revision_not_found", code="plot_thread_revision_not_found"
        )
    result = await plot_thread_tracker.reject_revision(
        db,
        revision=revision,
        user_id=user.id,
    )
    if result is None:
        raise NotFoundError(
            "plot_thread_revision_not_found", code="plot_thread_revision_not_found"
        )
    await db.flush()
    await db.refresh(revision)
    await db.commit()
    return revision


@router.post(
    "/{thread_id}/revisions/{revision_id}/rollback",
    response_model=PlotThreadRevisionResponse,
)
async def rollback_plot_thread_revision(
    project_id: str,
    thread_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    revision = await PlotThreadRevisionRepository(db).get(
        revision_id, organization_id=tenant.organization_id
    )
    if not revision or revision.item_id != thread_id or revision.project_id != project_id:
        raise NotFoundError(
            "plot_thread_revision_not_found", code="plot_thread_revision_not_found"
        )
    item = await plot_thread_tracker.rollback_to(
        db,
        organization_id=tenant.organization_id,
        revision=revision,
        user_id=user.id,
    )
    if item is None:
        raise NotFoundError(
            "plot_thread_revision_not_found", code="plot_thread_revision_not_found"
        )
    await db.flush()
    await db.refresh(revision)
    await db.commit()
    return revision
