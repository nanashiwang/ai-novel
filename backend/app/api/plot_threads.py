"""剧情线 / Plot Thread API。

NovelSpec 的"主线 / 副线 / 伏笔"用 PlotThread 表存。本 endpoint 提供
列表 / 创建 / 改 / 删，让用户在 Bible 页面直接维护故事中的暗线明线。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import PlotThreadRepository
from app.schemas.common import APIModel
from app.services import plot_thread_tracker

router = APIRouter(prefix="/projects/{project_id}/plot-threads", tags=["plot-threads"])


class PlotThreadPayload(APIModel):
    title: str = Field(min_length=1, max_length=200)
    thread_type: str = Field(default="main", max_length=64)
    description: str = Field(default="", max_length=4000)
    status: str = Field(default="open", max_length=32)
    related_characters: list[str] = Field(default_factory=list)
    expected_resolve_chapter: int | None = Field(default=None, ge=1)


class PlotThreadPatchPayload(APIModel):
    title: str | None = Field(default=None, max_length=200)
    thread_type: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=32)
    related_characters: list[str] | None = None
    expected_resolve_chapter: int | None = Field(default=None, ge=1)


class PlotThreadResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    title: str
    thread_type: str
    description: str
    status: str
    related_characters: list[str] = []
    expected_resolve_chapter: int | None = None


@router.get("", response_model=list[PlotThreadResponse])
async def list_plot_threads(
    project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep
):
    require_permission(user, "project:read", tenant)
    rows = await PlotThreadRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("", response_model=PlotThreadResponse, status_code=201)
async def create_plot_thread(
    project_id: str,
    payload: PlotThreadPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    entry = await PlotThreadRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return entry


@router.patch("/{thread_id}", response_model=PlotThreadResponse)
async def update_plot_thread(
    project_id: str,
    thread_id: str,
    payload: PlotThreadPatchPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = PlotThreadRepository(db)
    entry = await repo.get(thread_id, organization_id=tenant.organization_id)
    if not entry or entry.project_id != project_id:
        raise NotFoundError("plot_thread_not_found", code="plot_thread_not_found")
    patch = payload.model_dump(exclude_unset=True)
    # Sprint 12-C: 用户级编辑走 tracker，白名单字段写 applied revision。
    for field, new_value in patch.items():
        if field in plot_thread_tracker.PLOT_THREAD_TRACKABLE_FIELDS:
            await plot_thread_tracker.record_user_edit(
                db,
                organization_id=tenant.organization_id,
                project_id=project_id,
                item=entry,
                field=field,
                new_value=new_value,
                user_id=user.id,
            )
        else:
            setattr(entry, field, new_value)
    await db.flush()
    await db.commit()
    return entry


@router.delete("/{thread_id}", status_code=204)
async def delete_plot_thread(
    project_id: str,
    thread_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = PlotThreadRepository(db)
    entry = await repo.get(thread_id, organization_id=tenant.organization_id)
    if not entry or entry.project_id != project_id:
        raise NotFoundError("plot_thread_not_found", code="plot_thread_not_found")
    await repo.delete(thread_id, organization_id=tenant.organization_id)
    await db.commit()
