"""项目 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.api.pagination import Pagination, paginate
from app.contracts import MAX_OUTLINE_CHAPTERS
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
from app.schemas.common import APIModel
from app.schemas.generation import GenerationJobResponse
from app.schemas.project import (
    GenerateNovelRequest,
    ProjectCreate,
    ProjectResponse,
    SceneWriteRequest,
)
from app.services.generation.service import generation_service
from app.services.preflight import preflight_service
from app.services.story_direction.service import story_direction_service

router = APIRouter(prefix="/projects", tags=["projects"])


class GenerateBibleRequest(APIModel):
    estimate_words: int = Field(default=2000, ge=1, le=20000)
    topic: str = ""
    force_regenerate: bool = False
    # 创作偏好（全部可选）：让 LLM prompt 含具体约束，避免每次都生成
    # 同质化的"主角追真相"开局
    protagonist_archetype: str = Field(default="", max_length=400)
    reference_works: list[str] = Field(default_factory=list)
    forbidden_themes: list[str] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0.0, le=1.5)


class GenerateOutlineRequest(APIModel):
    # None → 由 activity 回落到 project.target_chapter_count 或 6
    target_chapters: int | None = Field(default=None, ge=1, le=MAX_OUTLINE_CHAPTERS)
    estimate_words: int = Field(default=3000, ge=1, le=20000)
    force_regenerate: bool = False


class GenerateScenePlanRequest(APIModel):
    # None 表示交给 AI 根据章节复杂度自动判断，后端仍限制在 1-8 个。
    scenes_per_chapter: int | None = Field(default=None, ge=1, le=8)
    expected_words: int = Field(default=1500, ge=300, le=10000)
    estimate_words: int = Field(default=2000, ge=1, le=20000)
    force_regenerate: bool = False


class AuditSceneRequest(APIModel):
    estimate_words: int = Field(default=500, ge=1, le=5000)


class PolishChapterRequest(APIModel):
    """Sprint 17-C 方案 3：章后润色 pass 请求。force=True 时绕过 dedupe。"""

    force: bool = False
    estimate_words: int = Field(default=24000, ge=1000, le=80000)


# Sprint 17-E：批量请求 schemas
class BatchScenePlanRequest(APIModel):
    chapter_indices: list[int] | None = None
    force_regenerate: bool = False
    scenes_per_chapter: int | None = Field(default=None, ge=2, le=8)
    expected_words: int = Field(default=1500, ge=300, le=10000)


class BatchSceneWriteRequest(APIModel):
    chapter_indices: list[int] | None = None
    scene_ids: list[str] | None = None
    target_words: int = Field(default=1500, ge=300, le=10000)


class BatchAuditRequest(APIModel):
    chapter_indices: list[int] | None = None
    scene_ids: list[str] | None = None


class BatchRewriteRequest(APIModel):
    chapter_indices: list[int] | None = None
    severity_threshold: str = Field(default="medium")
    target_words: int = Field(default=1200, ge=300, le=10000)


class BatchPolishRequest(APIModel):
    chapter_indices: list[int] | None = None
    force: bool = False


class RewriteSceneRequest(APIModel):
    target_words: int = Field(default=1200, ge=300, le=10000)
    estimate_words: int = Field(default=2000, ge=1, le=20000)


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
    personality: str
    motivation: str
    secret: str
    arc: str
    relationships: dict
    current_state: dict


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
        protagonist_archetype=payload.protagonist_archetype,
        reference_works=payload.reference_works,
        forbidden_themes=payload.forbidden_themes,
        temperature=payload.temperature,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/outline/generate",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def generate_outline(
    project_id: str,
    payload: GenerateOutlineRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_outline_job(
        db,
        user,
        tenant,
        project_id=project_id,
        target_chapters=payload.target_chapters,
        estimate_words=payload.estimate_words,
        force_regenerate=payload.force_regenerate,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/chapters/{chapter_id}/scenes/generate",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def generate_scene_plan(
    project_id: str,
    chapter_id: str,
    payload: GenerateScenePlanRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_scene_plan_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_id=chapter_id,
        scenes_per_chapter=payload.scenes_per_chapter,
        expected_words=payload.expected_words,
        estimate_words=payload.estimate_words,
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
    job = await generation_service.create_write_scene_job(
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


@router.post(
    "/{project_id}/scenes/{scene_id}/audit",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def audit_scene(
    project_id: str,
    scene_id: str,
    payload: AuditSceneRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_audit_scene_job(
        db,
        user,
        tenant,
        project_id=project_id,
        scene_id=scene_id,
        estimate_words=payload.estimate_words,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/chapters/{chapter_id}/polish",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def polish_chapter(
    project_id: str,
    chapter_id: str,
    payload: PolishChapterRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-C 方案 3：触发整章 N 场 draft 的章后润色。"""
    job = await generation_service.create_polish_chapter_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_id=chapter_id,
        force=payload.force,
        estimate_words=payload.estimate_words,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


class PolishedDraftResponse(APIModel):
    id: str
    chapter_id: str
    version_type: str
    status: str
    content: str
    word_count: int
    content_format: str
    created_at: str


@router.get(
    "/{project_id}/chapters/{chapter_id}/polished",
    response_model=PolishedDraftResponse | None,
)
async def get_polished_draft(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """返回该章最新的 polish 版（含 status=draft 或 applied）；不存在时返回 null。"""
    require_permission(user, "project:read", tenant)
    from sqlalchemy import desc, select  # noqa: PLC0415

    from app.models.draft_version import DraftVersion  # noqa: PLC0415

    stmt = (
        select(DraftVersion)
        .where(
            DraftVersion.organization_id == tenant.organization_id,
            DraftVersion.project_id == project_id,
            DraftVersion.chapter_id == chapter_id,
            DraftVersion.version_type == "polish",
            DraftVersion.status.in_(["draft", "applied"]),
        )
        .order_by(desc(DraftVersion.created_at))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        return None
    return PolishedDraftResponse(
        id=row.id,
        chapter_id=row.chapter_id or chapter_id,
        version_type=row.version_type,
        status=row.status,
        content=row.content,
        word_count=row.word_count,
        content_format=row.content_format,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.post(
    "/{project_id}/chapters/{chapter_id}/polished/{draft_id}/accept",
    response_model=PolishedDraftResponse,
)
async def accept_polished_draft(
    project_id: str,
    chapter_id: str,
    draft_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """接受指定润色版：标 status='applied'，同章其它 polish drafts 标 'superseded'。
    scene-level drafts 不动（保留追溯）。"""
    require_permission(user, "project:update", tenant)
    from sqlalchemy import select, update  # noqa: PLC0415

    from app.models.draft_version import DraftVersion  # noqa: PLC0415

    stmt = select(DraftVersion).where(
        DraftVersion.id == draft_id,
        DraftVersion.organization_id == tenant.organization_id,
        DraftVersion.project_id == project_id,
        DraftVersion.chapter_id == chapter_id,
        DraftVersion.version_type == "polish",
    )
    target = (await db.execute(stmt)).scalars().first()
    if not target:
        raise NotFoundError("polish_draft_not_found")
    # 同章其它 polish drafts → superseded
    await db.execute(
        update(DraftVersion)
        .where(
            DraftVersion.organization_id == tenant.organization_id,
            DraftVersion.project_id == project_id,
            DraftVersion.chapter_id == chapter_id,
            DraftVersion.version_type == "polish",
            DraftVersion.id != draft_id,
            DraftVersion.status == "draft",
        )
        .values(status="superseded")
    )
    target.status = "applied"
    await db.flush()
    await db.commit()
    return PolishedDraftResponse(
        id=target.id,
        chapter_id=target.chapter_id or chapter_id,
        version_type=target.version_type,
        status=target.status,
        content=target.content,
        word_count=target.word_count,
        content_format=target.content_format,
        created_at=target.created_at.isoformat() if target.created_at else "",
    )


# Sprint 17-E：批量生成 endpoints
@router.post(
    "/{project_id}/scenes/generate-all",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def batch_generate_scenes(
    project_id: str,
    payload: BatchScenePlanRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-E：批量为所有/指定 chapters 生成 scene plans。"""
    job = await generation_service.create_batch_scene_plan_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_indices=payload.chapter_indices,
        force_regenerate=payload.force_regenerate,
        scenes_per_chapter=payload.scenes_per_chapter,
        expected_words=payload.expected_words,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/scenes/write-all",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def batch_write_scenes(
    project_id: str,
    payload: BatchSceneWriteRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-E：批量为所有/指定 scenes 写正文。同章串行 + 跨章并发 3。"""
    job = await generation_service.create_batch_scene_write_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_indices=payload.chapter_indices,
        scene_ids=payload.scene_ids,
        target_words=payload.target_words,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/scenes/audit-all",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def batch_audit_scenes(
    project_id: str,
    payload: BatchAuditRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-E：批量审稿。"""
    job = await generation_service.create_batch_audit_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_indices=payload.chapter_indices,
        scene_ids=payload.scene_ids,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/scenes/rewrite-all-with-issues",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def batch_rewrite_scenes(
    project_id: str,
    payload: BatchRewriteRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-E：批量为有 open issues 的 scenes 触发 rewrite。"""
    job = await generation_service.create_batch_rewrite_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_indices=payload.chapter_indices,
        severity_threshold=payload.severity_threshold,
        target_words=payload.target_words,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


@router.post(
    "/{project_id}/chapters/polish-all",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def batch_polish_chapters(
    project_id: str,
    payload: BatchPolishRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-E：批量为所有 drafted 章节跑 polish_chapter。"""
    job = await generation_service.create_batch_polish_job(
        db,
        user,
        tenant,
        project_id=project_id,
        chapter_indices=payload.chapter_indices,
        force=payload.force,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response


class BatchJobProgressResponse(APIModel):
    id: str
    job_type: str
    status: str
    input_payload: dict | None = None
    output_payload: dict | None = None
    created_at: str
    updated_at: str


@router.get(
    "/{project_id}/batch-jobs/{job_id}",
    response_model=BatchJobProgressResponse,
)
async def get_batch_job_progress(
    project_id: str,
    job_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """Sprint 17-E：拉单个 batch_job 当前进度（无 SSE 时兜底）。"""
    require_permission(user, "project:read", tenant)
    job = await GenerationJobRepository(db).get(
        job_id, organization_id=tenant.organization_id
    )
    if not job or job.project_id != project_id:
        raise NotFoundError("job_not_found")
    return BatchJobProgressResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        input_payload=job.input_payload or {},
        output_payload=job.output_payload or {},
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
    )


@router.post(
    "/{project_id}/scenes/{scene_id}/rewrite",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def rewrite_scene(
    project_id: str,
    scene_id: str,
    payload: RewriteSceneRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    job = await generation_service.create_rewrite_scene_job(
        db,
        user,
        tenant,
        project_id=project_id,
        scene_id=scene_id,
        target_words=payload.target_words,
        estimate_words=payload.estimate_words,
    )
    await db.refresh(job)
    response = GenerationJobResponse.model_validate(job)
    await db.commit()
    return response



# --- Preflight & Direction Preview ---


class PreflightCheckItem(APIModel):
    label: str
    level: str  # ok / warn / block
    detail: str = ""


class PreflightNextAction(APIModel):
    kind: str
    label: str
    href_suffix: str


class PreflightResponse(APIModel):
    project_status: str
    plan_code: str
    quota_key: str
    quota_limit: int
    quota_used: int
    quota_reserved: int
    quota_available: int
    estimate_words: int
    target_chapter_count: int
    is_long_novel: bool
    can_generate: bool
    checks: list[PreflightCheckItem] = []
    next_action: PreflightNextAction | None = None


@router.get("/{project_id}/preflight", response_model=PreflightResponse)
async def preflight(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    job_type: str = Query(default="generate_bible"),
):
    """生成前检查：套餐 / 额度 / 项目状态 / 长篇风险 / 推荐下一步。"""
    require_permission(user, "project:read", tenant)
    project = await ProjectRepository(db).get(
        project_id, organization_id=tenant.organization_id
    )
    if not project:
        raise NotFoundError("project_not_found")
    report = await preflight_service.check(db, tenant, project, job_type=job_type)
    return report.as_dict()


class DirectionPreviewRequest(APIModel):
    topic: str = Field(default="", max_length=400)
    protagonist_archetype: str = Field(default="", max_length=400)
    reference_works: list[str] = Field(default_factory=list)
    forbidden_themes: list[str] = Field(default_factory=list)


class DirectionItem(APIModel):
    name: str
    summary: str
    selling_points: list[str] = []
    risk: str = ""
    recommended: bool = False


class DirectionPreviewResponse(APIModel):
    directions: list[DirectionItem] = []


@router.post(
    "/{project_id}/bible/preview-directions",
    response_model=DirectionPreviewResponse,
)
async def preview_directions(
    project_id: str,
    payload: DirectionPreviewRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """根据项目元数据 + 创作偏好生成 3 个候选方向，让用户选一个再生成圣经。

    成本远低于完整 generate_bible：不写库、不扣额度（按 ContentReview 视角免费），
    只生成简短的方向卡片。
    """
    require_permission(user, "project:read", tenant)
    project = await ProjectRepository(db).get(
        project_id, organization_id=tenant.organization_id
    )
    if not project:
        raise NotFoundError("project_not_found")
    directions = await story_direction_service.preview(
        db,
        project=project,
        topic=payload.topic,
        protagonist_archetype=payload.protagonist_archetype,
        reference_works=payload.reference_works,
        forbidden_themes=payload.forbidden_themes,
        tenant=tenant,
    )
    return {"directions": [d.__dict__ for d in directions]}
