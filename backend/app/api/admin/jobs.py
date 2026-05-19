from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_platform_admin
from app.repositories import GenerationJobRepository
from app.schemas.generation import GenerationJobResponse

router = APIRouter(prefix="/admin/generation-jobs", tags=["admin-generation-jobs"])


@router.get("", response_model=list[GenerationJobResponse])
async def jobs(
    user: CurrentUserDep,
    db: DbDep,
    organization_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
):
    """平台级 generation_jobs 列表。

    支持四类过滤，Admin 控制台据此做"按租户/项目/任务类型/状态"的对账。
    """
    require_platform_admin(user)
    rows = await GenerationJobRepository(db).list(
        limit=limit,
        organization_id=organization_id,
        project_id=project_id,
        job_type=job_type,
        status=status,
    )
    return rows


@router.post("/{job_id}/cancel", response_model=GenerationJobResponse)
async def cancel(job_id: str, user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    repo = GenerationJobRepository(db)
    job = await repo.get(job_id)
    if not job:
        raise NotFoundError("job_not_found")
    job.status = "cancelled"
    await db.commit()
    return job
