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

router = APIRouter(prefix="/projects/{project_id}/plot-threads", tags=["plot-threads"])


class PlotThreadPayload(APIModel):
    title: str = Field(min_length=1, max_length=200)
    thread_type: str = Field(default="main", max_length=64)
    description: str = Field(default="", max_length=4000)
    status: str = Field(default="open", max_length=32)
    related_characters: list[str] = Field(default_factory=list)


class PlotThreadPatchPayload(APIModel):
    title: str | None = Field(default=None, max_length=200)
    thread_type: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=32)
    related_characters: list[str] | None = None


class PlotThreadResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    title: str
    thread_type: str
    description: str
    status: str
    related_characters: list[str] = []


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
    for key, value in patch.items():
        setattr(entry, key, value)
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
