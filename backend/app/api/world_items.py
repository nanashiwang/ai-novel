"""世界观条目 API。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import WorldItemRepository
from app.schemas.common import APIModel
from app.services import world_tracker

router = APIRouter(prefix="/projects/{project_id}/world-items", tags=["world-items"])


class WorldItemPayload(APIModel):
    type: str
    name: str
    description: str = ""
    rules: dict = {}
    related_characters: list[str] = []
    importance: str = "medium"
    is_hard_rule: bool = False


class WorldItemResponse(WorldItemPayload):
    id: str
    organization_id: str
    project_id: str


@router.get("", response_model=list[WorldItemResponse])
async def list_world_items(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "project:read", tenant)
    rows = await WorldItemRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("", response_model=WorldItemResponse, status_code=201)
async def create_world_item(
    project_id: str,
    payload: WorldItemPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    item = await WorldItemRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return item


@router.patch("/{item_id}", response_model=WorldItemResponse)
async def update_world_item(
    project_id: str,
    item_id: str,
    payload: WorldItemPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = WorldItemRepository(db)
    item = await repo.get(item_id, organization_id=tenant.organization_id)
    if not item or item.project_id != project_id:
        raise NotFoundError("world_item_not_found")
    # Sprint 12-C: 用户级编辑走 tracker，每个变化字段都会写一条 applied revision，
    # 并把同字段的旧 applied 标 superseded。非白名单字段直接写到 ORM，不进 revision。
    values = payload.model_dump()
    for field, new_value in values.items():
        if field in world_tracker.WORLD_ITEM_TRACKABLE_FIELDS:
            await world_tracker.record_user_edit(
                db,
                organization_id=tenant.organization_id,
                project_id=project_id,
                item=item,
                field=field,
                new_value=new_value,
                user_id=user.id,
            )
        else:
            setattr(item, field, new_value)
    await db.flush()
    await db.commit()
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_world_item(
    project_id: str,
    item_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = WorldItemRepository(db)
    item = await repo.get(item_id, organization_id=tenant.organization_id)
    if not item or item.project_id != project_id:
        raise NotFoundError("world_item_not_found")
    await repo.delete(item_id, organization_id=tenant.organization_id)
    await db.commit()
