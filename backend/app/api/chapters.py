"""章节 & 卷 API。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import ChapterRepository, VolumeRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/projects/{project_id}", tags=["chapters"])


class VolumePayload(APIModel):
    volume_index: int
    title: str
    summary: str = ""
    goal: str = ""
    status: str = "planned"


class VolumeResponse(VolumePayload):
    id: str
    organization_id: str
    project_id: str


class ChapterPayload(APIModel):
    chapter_index: int
    title: str
    volume_id: str | None = None
    summary: str = ""
    goal: str = ""
    conflict: str = ""
    ending_hook: str = ""
    status: str = "planned"


class ChapterResponse(ChapterPayload):
    id: str
    organization_id: str
    project_id: str


# Volumes
@router.get("/volumes", response_model=list[VolumeResponse])
async def list_volumes(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "chapter:read", tenant)
    rows = await VolumeRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("/volumes", response_model=VolumeResponse, status_code=201)
async def create_volume(
    project_id: str,
    payload: VolumePayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "chapter:write", tenant)
    volume = await VolumeRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return volume


# Chapters
@router.get("/chapters", response_model=list[ChapterResponse])
async def list_chapters(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "chapter:read", tenant)
    rows = await ChapterRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("/chapters", response_model=ChapterResponse, status_code=201)
async def create_chapter(
    project_id: str,
    payload: ChapterPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "chapter:write", tenant)
    if payload.volume_id:
        volume = await VolumeRepository(db).get(
            payload.volume_id, organization_id=tenant.organization_id
        )
        if not volume or volume.project_id != project_id:
            raise NotFoundError("volume_not_found")
    chapter = await ChapterRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return chapter


@router.get("/chapters/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "chapter:read", tenant)
    chapter = await ChapterRepository(db).get(
        chapter_id, organization_id=tenant.organization_id
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    return chapter


@router.patch("/chapters/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    project_id: str,
    chapter_id: str,
    payload: ChapterPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "chapter:write", tenant)
    if payload.volume_id:
        volume = await VolumeRepository(db).get(
            payload.volume_id, organization_id=tenant.organization_id
        )
        if not volume or volume.project_id != project_id:
            raise NotFoundError("volume_not_found")
    chapter = await ChapterRepository(db).update(
        chapter_id,
        payload.model_dump(),
        organization_id=tenant.organization_id,
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    await db.commit()
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=204)
async def delete_chapter(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "chapter:write", tenant)
    repo = ChapterRepository(db)
    chapter = await repo.get(chapter_id, organization_id=tenant.organization_id)
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    await repo.delete(chapter_id, organization_id=tenant.organization_id)
    await db.commit()
