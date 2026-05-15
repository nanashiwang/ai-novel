from fastapi import APIRouter, HTTPException, status
from app.api.deps import CurrentUserDep, TenantDep
from app.core.permissions import require_permission
from app.repositories.memory_store import get_row, insert_row, list_rows
from app.schemas.generation import GenerationJobResponse
from app.schemas.project import GenerateNovelRequest, ProjectCreate, ProjectResponse, SceneWriteRequest
from app.services.generation.service import generation_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(tenant: TenantDep, user: CurrentUserDep) -> list[dict]:
    require_permission(user, "project:read")
    return list_rows("projects", tenant.organization_id)


@router.post("", response_model=ProjectResponse)
async def create_project(payload: ProjectCreate, tenant: TenantDep, user: CurrentUserDep) -> dict:
    require_permission(user, "project:create")
    return insert_row(
        "projects",
        {
            "organization_id": tenant.organization_id,
            "created_by": user.id,
            "title": payload.title,
            "genre": payload.genre,
            "target_word_count": payload.target_word_count,
            "target_chapter_count": payload.target_chapter_count,
            "language": "zh-CN",
            "style": payload.style,
            "status": "created",
        },
        "project",
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, tenant: TenantDep, user: CurrentUserDep) -> dict:
    require_permission(user, "project:read")
    project = get_row("projects", project_id, tenant.organization_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    return project


@router.post("/{project_id}/generate-full-novel", response_model=GenerationJobResponse)
async def generate_full_novel(
    project_id: str,
    payload: GenerateNovelRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
) -> dict:
    return generation_service.create_full_novel_job(user, tenant, project_id, payload.estimate_words)


@router.post("/{project_id}/scenes/{scene_id}/write", response_model=GenerationJobResponse)
async def write_scene(
    project_id: str,
    scene_id: str,
    payload: SceneWriteRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
) -> dict:
    return generation_service.create_scene_write_job(user, tenant, project_id, scene_id, payload.target_words)
