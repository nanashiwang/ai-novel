"""项目内 Memory / Continuity Issue / Draft Version / Export 路由。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import (
    ChapterRepository,
    ContinuityIssueRepository,
    DraftVersionRepository,
    ExportFileRepository,
    MemoryRepository,
    ProjectRepository,
    SceneRepository,
)
from app.schemas.common import APIModel
from app.services.exporter import exporter_service
from app.services.storage import get_storage

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
    chapter_id: str | None = None
    scene_id: str | None = None
    issue_type: str
    severity: str
    description: str
    suggested_fix: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    # 'text' = 历史纯文本数据（兼容路径）；'markdown' = 新编辑器 / AI 输出
    content_format: Literal["text", "markdown"] = "text"
    word_count: int = 0
    status: str = "draft"
    parent_version_id: str | None = None


class DraftVersionResponse(DraftVersionPayload):
    id: str
    organization_id: str
    project_id: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    file_size: int = 0


@router.get("/exports", response_model=list[ExportResponse])
async def list_exports(project_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    require_permission(user, "project:read", tenant)
    rows = await ExportFileRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("/exports", response_model=ExportResponse, status_code=201)
async def create_export(
    project_id: str,
    payload: ExportRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """同步生成 Markdown / TXT 导出。

    Sprint 5-B：CPU-bound 任务，不调 LLM、无 quota；同步返回 201 + 导出
    元数据。前端通过 file_url 拉取文件。
    Sprint 6 引入 storage 抽象：当 settings.minio_enabled=true 时上传到
    MinIO 并把 file_url 设为预签名 URL；否则继续把 content 存到
    ExportFile.content（db 模式），file_url 指向下面的 download endpoint。
    docx/epub/pdf 等格式留待真实部署时再加。
    """
    require_permission(user, "export:create", tenant)
    export_type = (payload.export_type or "markdown").lower().strip()
    if export_type not in {"markdown", "txt"}:
        raise NotFoundError("export_type_not_supported")

    project = await ProjectRepository(db).get(
        project_id, organization_id=tenant.organization_id
    )
    if not project:
        raise NotFoundError("project_not_found")

    content, file_size = await exporter_service.export_project(
        db,
        project=project,
        export_format=export_type,  # type: ignore[arg-type]
    )

    # 先 create db 行拿到 export_id（key 含此 id）
    exp = await ExportFileRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        export_type=export_type,
        file_url="",
        status="ready",
        created_by=user.id,
        content="",
        file_size=file_size,
    )

    storage = get_storage()
    settings = get_settings()
    suffix_by_type = {"markdown": "md", "txt": "txt"}
    mime_by_type = {"markdown": "text/markdown", "txt": "text/plain"}
    suffix = suffix_by_type.get(export_type, "txt")
    mime = mime_by_type.get(export_type, "application/octet-stream")
    object_key = (
        f"{tenant.organization_id}/{project_id}/{exp.id}.{suffix}"
    )

    if settings.minio_enabled:
        # MinIO 模式：上传到对象存储，file_url 用预签名 URL，content 字段留空
        await storage.put(
            object_key,
            content.encode("utf-8"),
            content_type=f"{mime}; charset=utf-8",
        )
        signed = await storage.sign_url(
            object_key,
            filename=f"{project_id}-{exp.id}.{suffix}",
            content_type=f"{mime}; charset=utf-8",
        )
        exp.file_url = signed or ""
    else:
        # db 模式：content 直接落 ExportFile.content，file_url 指向 download endpoint
        exp.content = content
        exp.file_url = f"/api/v1/projects/{project_id}/exports/{exp.id}/download"

    await db.commit()
    # Prometheus 埋点：导出成功（按 export_type）
    from app.core.metrics import EXPORTS_CREATED  # noqa: PLC0415

    EXPORTS_CREATED.labels(export_type=export_type).inc()
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


@router.get("/exports/{export_id}/download")
async def download_export(
    project_id: str,
    export_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """以文件流返回导出文件正文。

    Content-Type 与 Content-Disposition.filename 根据 export_type 推断。
    Sprint 5-B：从 db.content 流式输出；Sprint 6 切到 MinIO 预签名 URL 时
    本端点可直接 302 重定向到对象存储。
    """
    require_permission(user, "project:read", tenant)
    exp = await ExportFileRepository(db).get(
        export_id, organization_id=tenant.organization_id
    )
    if not exp or exp.project_id != project_id:
        raise NotFoundError("export_not_found")

    suffix_by_type = {"markdown": "md", "txt": "txt"}
    mime_by_type = {"markdown": "text/markdown", "txt": "text/plain"}
    suffix = suffix_by_type.get(exp.export_type, "txt")
    mime = mime_by_type.get(exp.export_type, "application/octet-stream")
    filename = f"{project_id}-{export_id}.{suffix}"

    payload = (exp.content or "").encode("utf-8")
    return StreamingResponse(
        iter([payload]),
        media_type=f"{mime}; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )
