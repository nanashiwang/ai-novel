"""项目 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.api.pagination import Pagination, paginate
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import (
    CharacterRepository,
    GenerationJobRepository,
    NovelSpecRepository,
    PlotThreadRepository,
    ProjectRepository,
    WorldItemRepository,
)
from app.schemas.generation import GenerationJobResponse
from app.schemas.common import APIModel
from app.schemas.project import (
    GenerateNovelRequest,
    ProjectCreate,
    ProjectResponse,
    SceneWriteRequest,
)
from app.services.generation.service import generation_service

router = APIRouter(prefix="/projects", tags=["projects"])


class GenerateBibleRequest(APIModel):
    estimate_words: int = Field(default=2000, ge=1, le=20000)
    topic: str = ""
    force_regenerate: bool = False


class BibleSpecResponse(APIModel):
    id: str
    premise: str
    theme: str
    genre: str
    tone: str
    target_reader: str
    narrative_pov: str
    style_guide: str
    constraints: list[str]
    continuity_rules: list[str] = []


class BibleCharacterResponse(APIModel):
    id: str
    name: str
    role: str
    description: str
    motivation: str
    arc: str


class BibleWorldItemResponse(APIModel):
    id: str
    type: str
    name: str
    description: str
    importance: str
    is_hard_rule: bool


class BiblePlotThreadResponse(APIModel):
    id: str
    title: str
    thread_type: str
    description: str
    status: str


class BibleResponse(APIModel):
    project_id: str
    project_status: str
    spec: BibleSpecResponse | None = None
    characters: list[BibleCharacterResponse] = []
    world_items: list[BibleWorldItemResponse] = []
    plot_threads: list[BiblePlotThreadResponse] = []
    latest_job: GenerationJobResponse | None = None


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
    if payload.premise:
        await NovelSpecRepository(db).create(
            organization_id=tenant.organization_id,
            project_id=project.id,
            premise=payload.premise,
            genre=payload.genre,
            target_reader=payload.target_reader,
            style_guide=payload.style,
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


@router.get("/{project_id}/bible", response_model=BibleResponse)
async def get_bible(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    project = await ProjectRepository(db).get(
        project_id, organization_id=tenant.organization_id
    )
    if not project:
        raise NotFoundError("project_not_found")

    spec = await NovelSpecRepository(db).get_by(
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    characters = await CharacterRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        limit=50,
    )
    world_items = await WorldItemRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        limit=50,
    )
    plot_threads = await PlotThreadRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        limit=50,
    )
    latest_jobs = await GenerationJobRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        job_type="generate_bible",
        limit=1,
    )
    return BibleResponse(
        project_id=project_id,
        project_status=project.status,
        spec=spec,
        characters=list(characters),
        world_items=list(world_items),
        plot_threads=list(plot_threads),
        latest_job=latest_jobs[0] if latest_jobs else None,
    )


@router.post(
    "/{project_id}/bible/generate",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def generate_bible(
    project_id: str,
    payload: GenerateBibleRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_bible_job(
        db,
        user,
        tenant,
        project_id=project_id,
        estimate_words=payload.estimate_words,
        topic=payload.topic,
        force_regenerate=payload.force_regenerate,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


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
        mode=payload.mode,
        topic=payload.topic,
        target_chapters=payload.target_chapters,
        scenes_per_chapter=payload.scenes_per_chapter,
        write_drafts=payload.write_drafts,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


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
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response
