"""项目 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.api.pagination import Pagination, paginate
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import ProjectRepository
from app.schemas.generation import GenerationJobResponse
from app.schemas.project import (
    GenerateNovelRequest,
    ProjectCreate,
    ProjectResponse,
    SceneWriteRequest,
)
from app.services.generation.service import generation_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    pagination: Pagination = Depends(paginate),
):
    require_permission(user, "project:read", tenant)
    rows = await ProjectRepository(db).list(
        organization_id=tenant.organization_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return rows


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate, tenant: TenantDep, user: CurrentUserDep, db: DbDep
):
    require_permission(user, "project:create", tenant)
    project = await ProjectRepository(db).create(
        organization_id=tenant.organization_id,
        created_by=user.id,
        title=payload.title,
        genre=payload.genre,
        target_word_count=payload.target_word_count,
        target_chapter_count=payload.target_chapter_count,
        language="zh-CN",
        style=payload.style,
        status="created",
        cover_url=payload.cover_url,
        tags=payload.tags,
        target_reader=payload.target_reader,
    )
    await db.commit()
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep
):
    require_permission(user, "project:read", tenant)
    project = await ProjectRepository(db).get(
        project_id, organization_id=tenant.organization_id
    )
    if not project:
        raise NotFoundError("project_not_found")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep
):
    require_permission(user, "project:delete", tenant)
    ok = await ProjectRepository(db).delete(
        project_id, organization_id=tenant.organization_id
    )
    if not ok:
        raise NotFoundError("project_not_found")
    await db.commit()


@router.post(
    "/{project_id}/generate-full-novel",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def generate_full_novel(
    project_id: str,
    payload: GenerateNovelRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_full_novel_job(
        db,
        user,
        tenant,
        project_id=project_id,
        estimate_words=payload.estimate_words,
    )
    await db.commit()
    return job


@router.post(
    "/{project_id}/scenes/{scene_id}/write",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def write_scene(
    project_id: str,
    scene_id: str,
    payload: SceneWriteRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_scene_write_job(
        db,
        user,
        tenant,
        project_id=project_id,
        scene_id=scene_id,
        target_words=payload.target_words,
    )
    await db.commit()
    return job
