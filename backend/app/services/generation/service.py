"""生成任务服务（ORM 化）。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.core.tenancy import TenantContext, ensure_same_tenant
from app.models.generation_job import GenerationJob
from app.repositories import GenerationJobRepository, ProjectRepository
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
    async def create_full_novel_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        estimate_words: int,
        mode: str = "full_novel",
        topic: str = "",
        target_chapters: int | None = None,
        scenes_per_chapter: int = 3,
        write_drafts: bool = True,
    ) -> GenerationJob:
        require_permission(user, "generation_job:create", tenant)
        require_entitlement(tenant, "generation:full_novel")

        project = await ProjectRepository(session).get(
            project_id, organization_id=tenant.organization_id
        )
        if not project:
            raise NotFoundError("project_not_found")
        ensure_same_tenant(project.organization_id, tenant)

        job = await GenerationJobRepository(session).create(
            organization_id=tenant.organization_id,
            user_id=user.id,
            project_id=project_id,
            job_type="full_novel",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={
                "estimate_words": estimate_words,
                "mode": mode,
                "topic": topic,
                "target_chapters": target_chapters,
                "scenes_per_chapter": scenes_per_chapter,
                "write_drafts": write_drafts,
            },
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=estimate_words,
        )
        job.workflow_id = workflow_starter.start_generate_full_novel({"id": job.id})
        await session.flush()
        if workflow_starter.is_mock_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("full_novel", job.id)
            )
        return job

    async def create_scene_write_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        scene_id: str,
        target_words: int,
    ) -> GenerationJob:
        require_permission(user, "generation_job:create", tenant)
        require_entitlement(tenant, "generation:scene")

        project = await ProjectRepository(session).get(
            project_id, organization_id=tenant.organization_id
        )
        if not project:
            raise NotFoundError("project_not_found")

        job = await GenerationJobRepository(session).create(
            organization_id=tenant.organization_id,
            user_id=user.id,
            project_id=project_id,
            job_type="scene_write",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=target_words,
            consumed_quota=0,
            input_payload={"scene_id": scene_id, "target_words": target_words},
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=target_words,
        )
        job.workflow_id = workflow_starter.start_write_scene({"id": job.id})
        await session.flush()
        if workflow_starter.is_mock_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("scene_write", job.id)
            )
        return job

    async def get_job(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        job_id: str,
    ) -> GenerationJob | None:
        return await GenerationJobRepository(session).get(
            job_id, organization_id=tenant.organization_id
        )

    async def list_jobs(
        self,
        session: AsyncSession,
        tenant: TenantContext | None = None,
        *,
        limit: int = 100,
    ) -> list[GenerationJob]:
        repo = GenerationJobRepository(session)
        org_id = tenant.organization_id if tenant else None
        rows = await repo.list(organization_id=org_id, limit=limit)
        return list(rows)

    async def cancel_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        job_id: str,
    ) -> GenerationJob | None:
        require_permission(user, "generation_job:cancel", tenant)
        job = await GenerationJobRepository(session).get(
            job_id, organization_id=tenant.organization_id
        )
        if not job:
            return None
        job.status = "cancelled"
        await session.flush()
        return job


generation_service = GenerationService()
