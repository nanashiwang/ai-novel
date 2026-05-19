"""项目内 Memory / Continuity Issue / Draft Version / Export 路由。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import (
    ChapterRepository,
    ContinuityIssueRepository,
    DraftVersionRepository,
    ExportFileRepository,
    MemoryRepository,
    SceneRepository,
)
from app.schemas.common import APIModel

router = APIRouter(prefix="/projects/{project_id}", tags=["project-extra"])


# --- Memory ---
class MemoryPayload(APIModel):
    source_type: str = "scene"
    source_id: str
    memory_type: str
    title: str
    content: str
    importance: int = 3


class MemoryResponse(MemoryPayload):
    id: str
    organization_id: str
    project_id: str


@router.get("/memory", response_model=list[MemoryResponse])
async def list_memory(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "memory:read", tenant)
    rows = await MemoryRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("/memory", response_model=MemoryResponse, status_code=201)
async def create_memory(
    project_id: str,
    payload: MemoryPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "memory:write", tenant)
    entry = await MemoryRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return entry


# --- Continuity issues ---
class ContinuityIssueResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    issue_type: str
    severity: str
    description: str
    suggested_fix: str
    status: str


@router.get("/continuity-issues", response_model=list[ContinuityIssueResponse])
async def list_continuity_issues(
    project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep
):
    require_permission(user, "project:read", tenant)
    rows = await ContinuityIssueRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


# --- Draft versions ---
class DraftVersionPayload(APIModel):
    chapter_id: str | None = None
    scene_id: str | None = None
    version_type: str = "draft"
    content: str = ""
    word_count: int = 0
    status: str = "draft"
    parent_version_id: str | None = None


class DraftVersionResponse(DraftVersionPayload):
    id: str
    organization_id: str
    project_id: str
    created_by: str


@router.get("/versions", response_model=list[DraftVersionResponse])
async def list_versions(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    chapter_id: str | None = None,
    scene_id: str | None = None,
):
    require_permission(user, "project:read", tenant)
    rows = await DraftVersionRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
        scene_id=scene_id,
    )
    return rows


@router.post("/versions", response_model=DraftVersionResponse, status_code=201)
async def create_version(
    project_id: str,
    payload: DraftVersionPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    if payload.chapter_id:
        chapter = await ChapterRepository(db).get(
            payload.chapter_id, organization_id=tenant.organization_id
        )
        if not chapter or chapter.project_id != project_id:
            raise NotFoundError("chapter_not_found")
    if payload.scene_id:
        scene = await SceneRepository(db).get(
            payload.scene_id, organization_id=tenant.organization_id
        )
        if not scene or scene.project_id != project_id:
            raise NotFoundError("scene_not_found")
    version = await DraftVersionRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        created_by=user.id,
        **payload.model_dump(),
    )
    await db.commit()
    return version


@router.get("/versions/{version_id}", response_model=DraftVersionResponse)
async def get_version(
    project_id: str,
    version_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    version = await DraftVersionRepository(db).get(
        version_id, organization_id=tenant.organization_id
    )
    if not version or version.project_id != project_id:
        raise NotFoundError("version_not_found")
    return version


@router.delete("/versions/{version_id}", status_code=204)
async def delete_version(
    project_id: str,
    version_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """删除单个 draft_version。

    场景：用户拒绝 AI 重生成的草稿、清理 autosave 噪音。
    多租户隔离：通过 organization_id 与 project_id 双重校验。
    """
    require_permission(user, "scene:write", tenant)
    repo = DraftVersionRepository(db)
    version = await repo.get(version_id, organization_id=tenant.organization_id)
    if not version or version.project_id != project_id:
        raise NotFoundError("version_not_found")
    await repo.delete(version_id, organization_id=tenant.organization_id)
    await db.commit()


# --- Exports ---
class ExportRequest(APIModel):
    export_type: str  # markdown / txt / docx / epub / pdf


class ExportResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    export_type: str
    file_url: str
    status: str
    created_by: str


@router.get("/exports", response_model=list[ExportResponse])
async def list_exports(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "project:read", tenant)
    rows = await ExportFileRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("/exports", response_model=ExportResponse, status_code=202)
async def create_export(
    project_id: str,
    payload: ExportRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "export:create", tenant)
    exp = await ExportFileRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        export_type=payload.export_type,
        file_url="",
        status="queued",
        created_by=user.id,
    )
    await db.commit()
    return exp


@router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    project_id: str,
    export_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    exp = await ExportFileRepository(db).get(
        export_id, organization_id=tenant.organization_id
    )
    if not exp or exp.project_id != project_id:
        raise NotFoundError("export_not_found")
    return exp
