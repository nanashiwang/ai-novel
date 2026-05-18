from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_platform_admin
from app.repositories import AuditLogRepository, ModelCallRepository

router = APIRouter(tags=["admin-logs"])


@router.get("/admin/model-calls")
async def model_calls(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await ModelCallRepository(db).list(limit=200)
    return [
        {
            "id": r.id,
            "organization_id": r.organization_id,
            "project_id": r.project_id,
            "job_id": r.job_id,
            "task_type": r.task_type,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "latency_ms": r.latency_ms,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/admin/audit-logs")
async def audit_logs(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await AuditLogRepository(db).list(limit=200)
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
