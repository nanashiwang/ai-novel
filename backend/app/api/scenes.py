"""场景 API。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import ChapterRepository, SceneRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["scenes"])


class ScenePayload(APIModel):
    chapter_id: str
    scene_index: int
    title: str
    time_marker: str = ""
    location: str = ""
    characters: list[str] = []
    scene_purpose: str = ""
    entry_state: str = ""
    exit_state: str = ""
    goal: str = ""
    conflict: str = ""
    must_include: list[str] = []
    must_avoid: list[str] = []
    emotion_start: str = ""
    emotion_end: str = ""
    reveal: str = ""
    hook: str = ""
    status: str = "planned"


class SceneResponse(ScenePayload):
    id: str
    organization_id: str
    project_id: str


@router.get("", response_model=list[SceneResponse])
async def list_scenes(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    chapter_id: str | None = None,
):
    require_permission(user, "scene:read", tenant)
    rows = await SceneRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return rows


@router.post("", response_model=SceneResponse, status_code=201)
async def create_scene(
    project_id: str,
    payload: ScenePayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    chapter = await ChapterRepository(db).get(
        payload.chapter_id, organization_id=tenant.organization_id
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    scene = await SceneRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return scene


@router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(
    project_id: str,
    scene_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:read", tenant)
    scene = await SceneRepository(db).get(scene_id, organization_id=tenant.organization_id)
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    return scene


@router.patch("/{scene_id}", response_model=SceneResponse)
async def update_scene(
    project_id: str,
    scene_id: str,
    payload: ScenePayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    chapter = await ChapterRepository(db).get(
        payload.chapter_id, organization_id=tenant.organization_id
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    scene = await SceneRepository(db).update(
        scene_id, payload.model_dump(), organization_id=tenant.organization_id
    )
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    await db.commit()
    return scene


@router.delete("/{scene_id}", status_code=204)
async def delete_scene(
    project_id: str,
    scene_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    repo = SceneRepository(db)
    scene = await repo.get(scene_id, organization_id=tenant.organization_id)
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    await repo.delete(scene_id, organization_id=tenant.organization_id)
    await db.commit()
