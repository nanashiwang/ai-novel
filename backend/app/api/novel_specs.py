"""故事圣经 / Book Spec API。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import NovelSpecRepository, ProjectRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/projects/{project_id}/spec", tags=["novel-specs"])


class NovelSpecPayload(APIModel):
    premise: str = ""
    theme: str = ""
    genre: str = ""
    tone: str = ""
    target_reader: str = ""
    narrative_pov: str = ""
    style_guide: str = ""
    constraints: list[str] = []
    continuity_rules: list[str] = []


class NovelSpecResponse(NovelSpecPayload):
    id: str
    organization_id: str
    project_id: str


async def _ensure_project(project_id: str, tenant: TenantDep, db: DbDep):
    project = await ProjectRepository(db).get(project_id, organization_id=tenant.organization_id)
    if not project:
        raise NotFoundError("project_not_found")
    return project


@router.get("", response_model=NovelSpecResponse)
async def get_spec(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "project:read", tenant)
    await _ensure_project(project_id, tenant, db)
    spec = await NovelSpecRepository(db).get_by(
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    if not spec:
        raise NotFoundError("novel_spec_not_found")
    return spec


@router.put("", response_model=NovelSpecResponse)
async def upsert_spec(
    project_id: str,
    payload: NovelSpecPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _ensure_project(project_id, tenant, db)
    repo = NovelSpecRepository(db)
    spec = await repo.get_by(
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    values = payload.model_dump()
    if spec:
        for key, value in values.items():
            setattr(spec, key, value)
        await db.flush()
    else:
        spec = await repo.create(
            organization_id=tenant.organization_id,
            project_id=project_id,
            **values,
        )
    await db.commit()
    return spec
