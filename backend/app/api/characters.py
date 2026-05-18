"""人物卡 API。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import CharacterRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/projects/{project_id}/characters", tags=["characters"])


class CharacterPayload(APIModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = ""
    description: str = ""
    personality: str = ""
    motivation: str = ""
    secret: str = ""
    arc: str = ""
    relationships: dict = {}
    current_state: dict = {}


class CharacterResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    name: str
    role: str
    description: str
    personality: str
    motivation: str
    secret: str
    arc: str
    relationships: dict
    current_state: dict


@router.get("", response_model=list[CharacterResponse])
async def list_characters(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "character:read", tenant)
    rows = await CharacterRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("", response_model=CharacterResponse, status_code=201)
async def create_character(
    project_id: str,
    payload: CharacterPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "character:write", tenant)
    character = await CharacterRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return character


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character(
    project_id: str,
    character_id: str,
    payload: CharacterPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "character:write", tenant)
    character = await CharacterRepository(db).update(
        character_id,
        payload.model_dump(),
        organization_id=tenant.organization_id,
    )
    if not character or character.project_id != project_id:
        raise NotFoundError("character_not_found")
    await db.commit()
    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    project_id: str,
    character_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "character:write", tenant)
    repo = CharacterRepository(db)
    character = await repo.get(character_id, organization_id=tenant.organization_id)
    if not character or character.project_id != project_id:
        raise NotFoundError("character_not_found")
    await repo.delete(character_id, organization_id=tenant.organization_id)
    await db.commit()
