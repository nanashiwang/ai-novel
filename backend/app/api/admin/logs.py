from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_platform_admin
from app.repositories import AuditLogRepository, ModelCallRepository

router = APIRouter(tags=["admin-logs"])


@router.get("/admin/model-calls")
async def model_calls(
    user: CurrentUserDep,
    db: DbDep,
    project_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """平台级 model_calls 列表。

    支持按 project_id / job_id / organization_id / task_type 过滤，
    用于在 Admin 控制台对某个项目或单个 job 做 drill-down。BaseRepository.list
    会自动跳过值为 None 的 filter，所以这里直接透传即可。
    """
    require_platform_admin(user)
    rows = await ModelCallRepository(db).list(
        limit=limit,
        project_id=project_id,
        job_id=job_id,
        organization_id=organization_id,
        task_type=task_type,
    )
    return [
        {
            "id": r.id,
            "organization_id": r.organization_id,
            "project_id": r.project_id,
            "job_id": r.job_id,
            "task_type": r.task_type,
            "model": r.model,
            "prompt_key": r.prompt_key,
            "prompt_version": r.prompt_version,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "latency_ms": r.latency_ms,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/admin/audit-logs")
async def audit_logs(
    user: CurrentUserDep,
    db: DbDep,
    organization_id: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    require_platform_admin(user)
    rows = await AuditLogRepository(db).list(
        limit=limit,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
    )
    return [
        {
            "id": r.id,
            "organization_id": r.organization_id,
            "actor_user_id": r.actor_user_id,
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "before_data": r.before_data,
            "after_data": r.after_data,
            "created_at": r.created_at,
        }
        for r in rows
    ]
