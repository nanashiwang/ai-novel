from __future__ import annotations

from fastapi import HTTPException, status

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.core.tenancy import TenantContext, ensure_same_tenant
from app.repositories.memory_store import get_row, insert_row, list_rows, update_row
from app.services.entitlement.service import require_entitlement
from app.services.quota.service import quota_service
from app.workflows.starter import workflow_starter

PLAN_QUEUE = {
    "Free": "queue_free",
    "Starter": "queue_standard",
    "Pro": "queue_pro",
    "Team": "queue_team",
    "Enterprise": "queue_enterprise",
}


class GenerationService:
    def create_full_novel_job(
        self,
        user: CurrentUser,
        tenant: TenantContext,
        project_id: str,
        estimate_words: int,
    ) -> dict:
        require_permission(user, "generation_job:create")
        require_entitlement(tenant, "generation:full_novel")
        project = get_row("projects", project_id, tenant.organization_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
        ensure_same_tenant(project["organization_id"], tenant)
        job = insert_row(
            "generation_jobs",
            {
                "organization_id": tenant.organization_id,
                "user_id": user.id,
                "project_id": project_id,
                "job_type": "full_novel",
                "status": "queued",
                "priority": PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
                "plan_code": tenant.plan_code,
                "reserved_quota": estimate_words,
                "consumed_quota": 0,
                "input_payload": {"estimate_words": estimate_words},
            },
            "job",
        )
        quota_service.reserve_quota(tenant, job["id"], "monthly_generated_words", estimate_words)
        workflow_id = workflow_starter.start_generate_full_novel(job)
        return update_row("generation_jobs", job["id"], {"workflow_id": workflow_id}) or job

    def create_scene_write_job(
        self,
        user: CurrentUser,
        tenant: TenantContext,
        project_id: str,
        scene_id: str,
        target_words: int,
    ) -> dict:
        require_permission(user, "generation_job:create")
        require_entitlement(tenant, "generation:scene")
        job = insert_row(
            "generation_jobs",
            {
                "organization_id": tenant.organization_id,
                "user_id": user.id,
                "project_id": project_id,
                "job_type": "scene_write",
                "status": "queued",
                "priority": PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
                "plan_code": tenant.plan_code,
                "reserved_quota": target_words,
                "consumed_quota": 0,
                "input_payload": {"scene_id": scene_id, "target_words": target_words},
            },
            "job",
        )
        quota_service.reserve_quota(tenant, job["id"], "monthly_generated_words", target_words)
        workflow_id = workflow_starter.start_write_scene(job)
        return update_row("generation_jobs", job["id"], {"workflow_id": workflow_id}) or job

    def get_job(self, tenant: TenantContext, job_id: str) -> dict | None:
        return get_row("generation_jobs", job_id, tenant.organization_id)

    def list_jobs(self, tenant: TenantContext | None = None) -> list[dict]:
        return list_rows("generation_jobs", tenant.organization_id if tenant else None)

    def cancel_job(self, user: CurrentUser, tenant: TenantContext, job_id: str) -> dict | None:
        require_permission(user, "generation_job:cancel")
        job = get_row("generation_jobs", job_id, tenant.organization_id)
        if not job:
            return None
        return update_row(
            "generation_jobs",
            job_id,
            {"status": "cancelled"},
            tenant.organization_id,
        )


generation_service = GenerationService()
