"""生成任务服务（ORM 化）。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.core.tenancy import TenantContext, ensure_same_tenant
from app.models.generation_job import GenerationJob
from app.repositories import (
    ChapterRepository,
    GenerationJobRepository,
    NovelSpecRepository,
    ProjectRepository,
)
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
    async def create_bible_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        estimate_words: int = 2000,
        topic: str = "",
        force_regenerate: bool = False,
    ) -> GenerationJob:
        require_permission(user, "generation_job:create", tenant)

        project = await ProjectRepository(session).get(
            project_id, organization_id=tenant.organization_id
        )
        if not project:
            raise NotFoundError("project_not_found")
        ensure_same_tenant(project.organization_id, tenant)

        estimate_words = max(1, estimate_words)
        job = await GenerationJobRepository(session).create(
            organization_id=tenant.organization_id,
            user_id=user.id,
            project_id=project_id,
            job_type="generate_bible",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={
                "estimate_words": estimate_words,
                "topic": topic,
                "force_regenerate_spec": force_regenerate,
            },
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=estimate_words,
        )
        project.status = "bible_generating"
        job.workflow_id = workflow_starter.start_generate_bible({"id": job.id})
        await session.flush()
        if workflow_starter.is_mock_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("generate_bible", job.id)
            )
        return job

    async def create_outline_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        target_chapters: int | None = None,
        estimate_words: int = 3000,
        force_regenerate: bool = False,
    ) -> GenerationJob:
        """启动章节大纲生成任务。

        前置：项目必须已经有 NovelSpec（即 generate_bible 已完成）。
        参数：
            target_chapters: 期望章节数，None 时回落到 project.target_chapter_count 或 6；
                activity 内 clamp 到 [1, 12]。
            estimate_words: 用于 quota 预留；与 outline 本身的成本估算相关，
                而非实际章节字数。
            force_regenerate: True 时即使已有 chapters 也重新生成，绕过 reuse 分支。
        """
        require_permission(user, "generation_job:create", tenant)

        project = await ProjectRepository(session).get(
            project_id, organization_id=tenant.organization_id
        )
        if not project:
            raise NotFoundError("project_not_found")
        ensure_same_tenant(project.organization_id, tenant)

        spec = await NovelSpecRepository(session).get_by(
            organization_id=tenant.organization_id,
            project_id=project_id,
        )
        if not spec:
            raise NotFoundError("novel_spec_not_found")

        estimate_words = max(1, estimate_words)
        job = await GenerationJobRepository(session).create(
            organization_id=tenant.organization_id,
            user_id=user.id,
            project_id=project_id,
            job_type="generate_outline",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={
                "estimate_words": estimate_words,
                "target_chapters": target_chapters,
                # activities.generate_chapter_outline 读的是 force_regenerate_outline
                "force_regenerate_outline": force_regenerate,
            },
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=estimate_words,
        )
        project.status = "outline_generating"
        job.workflow_id = workflow_starter.start_generate_outline({"id": job.id})
        await session.flush()
        if workflow_starter.is_mock_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("generate_outline", job.id)
            )
        return job

    async def create_scene_plan_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        chapter_id: str,
        scenes_per_chapter: int = 3,
        expected_words: int = 1500,
        estimate_words: int = 2000,
        force_regenerate: bool = False,
    ) -> GenerationJob:
        """单章场景计划生成任务。

        前置：
        - project 存在且属于当前 tenant
        - NovelSpec 已存在（generate_bible 已完成）
        - chapter 存在且属于该 project

        说明：不改变 project.status —— 单章生成是"局部更新"，让用户能逐章
        生成而不影响整体状态机。
        """
        require_permission(user, "generation_job:create", tenant)

        project = await ProjectRepository(session).get(
            project_id, organization_id=tenant.organization_id
        )
        if not project:
            raise NotFoundError("project_not_found")
        ensure_same_tenant(project.organization_id, tenant)

        spec = await NovelSpecRepository(session).get_by(
            organization_id=tenant.organization_id,
            project_id=project_id,
        )
        if not spec:
            raise NotFoundError("novel_spec_not_found")

        chapter = await ChapterRepository(session).get(
            chapter_id, organization_id=tenant.organization_id
        )
        if not chapter or chapter.project_id != project_id:
            raise NotFoundError("chapter_not_found")

        estimate_words = max(1, estimate_words)
        job = await GenerationJobRepository(session).create(
            organization_id=tenant.organization_id,
            user_id=user.id,
            project_id=project_id,
            job_type="generate_scene_plan",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={
                "chapter_id": chapter_id,
                "scenes_per_chapter": scenes_per_chapter,
                "expected_words": expected_words,
                "estimate_words": estimate_words,
                "force_regenerate_scenes": force_regenerate,
            },
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=estimate_words,
        )
        job.workflow_id = workflow_starter.start_generate_scene_plan({"id": job.id})
        await session.flush()
        if workflow_starter.is_mock_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("generate_scene_plan", job.id)
            )
        return job

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

    async def create_write_scene_job(
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
        ensure_same_tenant(project.organization_id, tenant)

        job = await GenerationJobRepository(session).create(
            organization_id=tenant.organization_id,
            user_id=user.id,
            project_id=project_id,
            job_type="write_scene",
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
                ("write_scene", job.id)
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
