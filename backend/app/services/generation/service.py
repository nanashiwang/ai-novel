"""生成任务服务（ORM 化）。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
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


def _compute_dedupe_key(
    *,
    organization_id: str,
    project_id: str,
    job_type: str,
    target_id: str = "",
    canonical_input: dict[str, Any] | None = None,
) -> str:
    """计算业务幂等键。

    用 sha256 截 32 字符，对 (organization, project, job_type, target,
    canonical_input) 做 deterministic 哈希。canonical_input 应只包含影响
    业务语义的字段（如 topic / target_words / force_regenerate）；retry_of
    / 时间戳等不应进入。
    """
    payload = json.dumps(
        {
            "org": organization_id,
            "project": project_id,
            "job_type": job_type,
            "target": target_id or "",
            "input": canonical_input or {},
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


async def _find_active_by_dedupe_key(
    session: AsyncSession,
    *,
    organization_id: str,
    dedupe_key: str,
) -> GenerationJob | None:
    """查询同租户下同 dedupe_key 且仍活跃（queued/running）的任务。"""
    stmt = (
        select(GenerationJob)
        .where(
            GenerationJob.organization_id == organization_id,
            GenerationJob.dedupe_key == dedupe_key,
            GenerationJob.status.in_(["queued", "running"]),
        )
        .order_by(GenerationJob.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


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
        protagonist_archetype: str = "",
        reference_works: list[str] | None = None,
        forbidden_themes: list[str] | None = None,
        temperature: float | None = None,
    ) -> GenerationJob:
        require_permission(user, "generation_job:create", tenant)

        project = await ProjectRepository(session).get(
            project_id, organization_id=tenant.organization_id
        )
        if not project:
            raise NotFoundError("project_not_found")
        ensure_same_tenant(project.organization_id, tenant)

        estimate_words = max(1, estimate_words)
        # 创作偏好参与去重 key：改了任何偏好都视为新意图，应触发新 job
        creative_prefs: dict = {
            "protagonist_archetype": (protagonist_archetype or "").strip(),
            "reference_works": [s.strip() for s in (reference_works or []) if s.strip()],
            "forbidden_themes": [s.strip() for s in (forbidden_themes or []) if s.strip()],
            "temperature": temperature,
        }
        dedupe = _compute_dedupe_key(
            organization_id=tenant.organization_id,
            project_id=project_id,
            job_type="generate_bible",
            canonical_input={
                "topic": topic,
                "force_regenerate_spec": force_regenerate,
                "creative_prefs": creative_prefs,
            },
        )
        existing = await _find_active_by_dedupe_key(
            session,
            organization_id=tenant.organization_id,
            dedupe_key=dedupe,
        )
        if existing is not None:
            return existing

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
                "creative_prefs": creative_prefs,
            },
            dedupe_key=dedupe,
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
        if workflow_starter.is_local_workflow(job.workflow_id):
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
                activity 内 clamp 到服务端大纲章节上限。
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
        dedupe = _compute_dedupe_key(
            organization_id=tenant.organization_id,
            project_id=project_id,
            job_type="generate_outline",
            canonical_input={
                "target_chapters": target_chapters,
                "force_regenerate_outline": force_regenerate,
            },
        )
        existing = await _find_active_by_dedupe_key(
            session,
            organization_id=tenant.organization_id,
            dedupe_key=dedupe,
        )
        if existing is not None:
            return existing

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
            dedupe_key=dedupe,
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
        if workflow_starter.is_local_workflow(job.workflow_id):
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
        scenes_per_chapter: int | None = None,
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
        dedupe = _compute_dedupe_key(
            organization_id=tenant.organization_id,
            project_id=project_id,
            job_type="generate_scene_plan",
            target_id=chapter_id,
            canonical_input={
                "scenes_per_chapter": scenes_per_chapter,
                "expected_words": expected_words,
                "force_regenerate_scenes": force_regenerate,
            },
        )
        existing = await _find_active_by_dedupe_key(
            session,
            organization_id=tenant.organization_id,
            dedupe_key=dedupe,
        )
        if existing is not None:
            return existing

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
            dedupe_key=dedupe,
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
        if workflow_starter.is_local_workflow(job.workflow_id):
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
        scenes_per_chapter: int | None = None,
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
        if workflow_starter.is_local_workflow(job.workflow_id):
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

        dedupe = _compute_dedupe_key(
            organization_id=tenant.organization_id,
            project_id=project_id,
            job_type="write_scene",
            target_id=scene_id,
            canonical_input={"target_words": target_words},
        )
        existing = await _find_active_by_dedupe_key(
            session,
            organization_id=tenant.organization_id,
            dedupe_key=dedupe,
        )
        if existing is not None:
            return existing

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
            dedupe_key=dedupe,
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
        if workflow_starter.is_local_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("write_scene", job.id)
            )
        return job

    async def create_audit_scene_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        scene_id: str,
        estimate_words: int = 500,
    ) -> GenerationJob:
        """对单 scene 的最新 draft 触发审稿。

        前置：scene 必须存在并属于该 project。activity 会进一步要求该 scene
        已有至少一个 draft；如果没有则抛 draft_not_found。
        """
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
            job_type="audit_scene",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={"scene_id": scene_id, "estimate_words": estimate_words},
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=estimate_words,
        )
        job.workflow_id = workflow_starter.start_audit_scene({"id": job.id})
        await session.flush()
        if workflow_starter.is_local_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("audit_scene", job.id)
            )
        return job

    async def create_rewrite_scene_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        project_id: str,
        scene_id: str,
        target_words: int = 1200,
        estimate_words: int = 2000,
    ) -> GenerationJob:
        """基于 scene 的 open issues 触发重写。

        Sprint 5-A：activity 自动捞所有 open issues，无需调用方筛选；
        Sprint 5+ 再支持"只修复某几条"的细粒度。
        """
        require_permission(user, "generation_job:create", tenant)
        require_entitlement(tenant, "generation:scene")
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
            job_type="rewrite_scene",
            status="queued",
            priority=PLAN_QUEUE.get(tenant.plan_code, "queue_standard"),
            plan_code=tenant.plan_code,
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={
                "scene_id": scene_id,
                "target_words": target_words,
                "estimate_words": estimate_words,
            },
        )
        await quota_service.reserve_quota(
            session,
            tenant,
            job_id=job.id,
            quota_key="monthly_generated_words",
            amount=estimate_words,
        )
        job.workflow_id = workflow_starter.start_rewrite_scene({"id": job.id})
        await session.flush()
        if workflow_starter.is_local_workflow(job.workflow_id):
            session.sync_session.info.setdefault("after_commit_tasks", []).append(
                ("rewrite_scene", job.id)
            )
        return job

    async def retry_job(
        self,
        session: AsyncSession,
        user: CurrentUser,
        tenant: TenantContext,
        *,
        job: GenerationJob,
    ) -> GenerationJob:
        """根据原 job 的 job_type 与 input_payload 重新创建一个同类型任务。

        Sprint 6-A：不复用原 job 行（status/quota 状态机已结束）；新建后
        通过 input_payload.retry_of 记录溯源链。仅允许 failed / cancelled
        状态的 job 触发；succeeded 的 job 想"重生成"应该让用户直接调
        force_regenerate=true 的对应 endpoint。
        """
        if job.status not in {"failed", "cancelled"}:
            raise ConflictError("job_not_retryable")

        payload = dict(job.input_payload or {})

        if job.job_type == "generate_bible":
            new_job = await self.create_bible_job(
                session, user, tenant,
                project_id=job.project_id,
                estimate_words=int(payload.get("estimate_words") or 2000),
                topic=str(payload.get("topic") or ""),
                force_regenerate=bool(payload.get("force_regenerate_spec")),
            )
        elif job.job_type == "generate_outline":
            new_job = await self.create_outline_job(
                session, user, tenant,
                project_id=job.project_id,
                target_chapters=payload.get("target_chapters"),
                estimate_words=int(payload.get("estimate_words") or 3000),
                force_regenerate=bool(payload.get("force_regenerate_outline")),
            )
        elif job.job_type == "generate_scene_plan":
            new_job = await self.create_scene_plan_job(
                session, user, tenant,
                project_id=job.project_id,
                chapter_id=str(payload.get("chapter_id") or ""),
                scenes_per_chapter=(
                    int(payload["scenes_per_chapter"])
                    if payload.get("scenes_per_chapter") is not None
                    else None
                ),
                expected_words=int(payload.get("expected_words") or 1500),
                estimate_words=int(payload.get("estimate_words") or 2000),
                force_regenerate=bool(payload.get("force_regenerate_scenes")),
            )
        elif job.job_type == "write_scene":
            new_job = await self.create_write_scene_job(
                session, user, tenant,
                project_id=job.project_id,
                scene_id=str(payload.get("scene_id") or ""),
                target_words=int(payload.get("target_words") or 1200),
            )
        elif job.job_type == "audit_scene":
            new_job = await self.create_audit_scene_job(
                session, user, tenant,
                project_id=job.project_id,
                scene_id=str(payload.get("scene_id") or ""),
                estimate_words=int(payload.get("estimate_words") or 500),
            )
        elif job.job_type == "rewrite_scene":
            new_job = await self.create_rewrite_scene_job(
                session, user, tenant,
                project_id=job.project_id,
                scene_id=str(payload.get("scene_id") or ""),
                target_words=int(payload.get("target_words") or 1200),
                estimate_words=int(payload.get("estimate_words") or 2000),
            )
        elif job.job_type == "full_novel":
            new_job = await self.create_full_novel_job(
                session, user, tenant,
                project_id=job.project_id,
                estimate_words=int(payload.get("estimate_words") or 20000),
                mode=str(payload.get("mode") or "full_novel"),
                topic=str(payload.get("topic") or ""),
                target_chapters=payload.get("target_chapters"),
                scenes_per_chapter=(
                    int(payload["scenes_per_chapter"])
                    if payload.get("scenes_per_chapter") is not None
                    else None
                ),
                write_drafts=bool(payload.get("write_drafts", True)),
            )
        else:
            raise ConflictError("unknown_job_type")

        # 在新 job 的 input_payload 上追加 retry_of 溯源；create_* 系列内部
        # 不读这个字段，所以单独打补丁不会影响业务逻辑。
        new_job.input_payload = {
            **(new_job.input_payload or {}),
            "retry_of": job.id,
        }
        await session.flush()
        return new_job

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
