"""Temporal Workflow Starter。

- TEMPORAL_ENABLED=false（默认）：返回 local workflow_id，使用进程内本地执行
- TEMPORAL_ENABLED=true：通过 temporalio 客户端启动真实 workflow

设计：starter 不直接 await client 启动结果，使用 fire-and-forget，
workflow_id 立即返回；任务状态由 worker 异步回写 generation_jobs。

可靠性约定：
1. asyncio.create_task() 返回的 task 必须被 starter 实例持有，
   否则 CPython GC 可能中途回收任务（Python 官方文档警告）。
2. 若 Temporal 启动失败（连接超时、提交报错），starter 会调用
   mark_job_status 把对应 generation_jobs 标记为 failed，避免 db 显示
   queued/running 但实际无人执行；mark_job_status 同时释放预留额度。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import get_settings

_logger = logging.getLogger(__name__)


class WorkflowStarter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        # 持有 fire-and-forget task 引用，防止被 GC 中途回收。
        # task 完成后通过 add_done_callback 自动 discard。
        self._pending_tasks: set[asyncio.Task[Any]] = set()

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.temporal_enabled:
            return None
        try:
            from temporalio.client import Client  # type: ignore

            self._client = await Client.connect(
                self.settings.temporal_host,
                namespace=self.settings.temporal_namespace,
            )
            return self._client
        except Exception:  # noqa: BLE001
            _logger.exception("failed_to_connect_temporal")
            return None

    async def _mark_job_failed(self, job_id: str, reason: str) -> None:
        """启动 workflow 失败时把 job 标记 failed，触发 quota 释放。"""
        try:
            from app.workflows.activities import mark_job_status  # noqa: PLC0415

            await mark_job_status(job_id, "failed", reason)
        except Exception:  # noqa: BLE001
            _logger.exception(
                "mark_job_failed_fallback_failed", extra={"job_id": job_id}
            )

    async def _start(
        self,
        workflow_name: str,
        args: list[Any],
        workflow_id: str,
        job_id: str,
    ) -> None:
        client = await self._get_client()
        if not client:
            await self._mark_job_failed(job_id, "temporal_unavailable")
            return
        try:
            await client.start_workflow(
                workflow_name,
                args=args,
                id=workflow_id,
                task_queue="novelflow-generation",
            )
        except Exception:  # noqa: BLE001
            _logger.exception(
                "failed_to_start_workflow",
                extra={"workflow": workflow_name, "job_id": job_id},
            )
            await self._mark_job_failed(job_id, "failed_to_start_workflow")

    def _fire_and_forget(self, workflow_name: str, job: dict, prefix: str) -> str:
        workflow_id = f"{prefix}-{job['id']}"
        if not self.settings.temporal_enabled:
            return f"local-{workflow_id}"
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._start(workflow_name, [job], workflow_id, job["id"])
            )
            self._track_task(task)
            return workflow_id
        except RuntimeError:
            return f"local-{workflow_id}"

    def start_generate_full_novel(self, job: dict) -> str:
        return self._fire_and_forget("GenerateFullNovelWorkflow", job, "generate-full-novel")

    def start_generate_bible(self, job: dict) -> str:
        return self._fire_and_forget("GenerateBibleWorkflow", job, "generate-bible")

    def start_revision_rewrite_proposal(self, job: dict) -> str:
        return self._fire_and_forget(
            "RevisionRewriteProposalWorkflow", job, "revision-rewrite-proposal"
        )

    def start_generate_outline(self, job: dict) -> str:
        return self._fire_and_forget("GenerateOutlineWorkflow", job, "generate-outline")

    def start_generate_scene_plan(self, job: dict) -> str:
        return self._fire_and_forget(
            "GenerateScenePlanWorkflow", job, "generate-scene-plan"
        )

    def start_write_scene(self, job: dict) -> str:
        return self._fire_and_forget("WriteSceneWorkflow", job, "write-scene")

    def start_audit_scene(self, job: dict) -> str:
        return self._fire_and_forget("AuditSceneWorkflow", job, "audit-scene")

    def start_rewrite_scene(self, job: dict) -> str:
        return self._fire_and_forget("RewriteSceneWorkflow", job, "rewrite-scene")

    def start_polish_chapter(self, job: dict) -> str:
        return self._fire_and_forget("PolishChapterWorkflow", job, "polish-chapter")

    def is_local_workflow(self, workflow_id: str | None) -> bool:
        return bool(workflow_id and workflow_id.startswith("local-"))

    def run_local_generate_full_novel(self, job_id: str) -> None:
        self._run_local("full_novel", job_id)

    def run_local_generate_bible(self, job_id: str) -> None:
        self._run_local("generate_bible", job_id)

    def run_local_revision_rewrite_proposal(self, job_id: str) -> None:
        self._run_local("revision_rewrite_proposal", job_id)

    def run_local_generate_outline(self, job_id: str) -> None:
        self._run_local("generate_outline", job_id)

    def run_local_generate_scene_plan(self, job_id: str) -> None:
        self._run_local("generate_scene_plan", job_id)

    def run_local_write_scene(self, job_id: str) -> None:
        self._run_local("write_scene", job_id)

    def run_local_audit_scene(self, job_id: str) -> None:
        self._run_local("audit_scene", job_id)

    def run_local_rewrite_scene(self, job_id: str) -> None:
        self._run_local("rewrite_scene", job_id)

    def run_local_polish_chapter(self, job_id: str) -> None:
        self._run_local("polish_chapter", job_id)

    def _run_local(self, job_type: str, job_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _logger.warning("local_workflow_skipped_no_event_loop", extra={"job_id": job_id})
            return
        task = loop.create_task(self._execute_local(job_type, job_id))
        self._track_task(task)

    async def _execute_local(self, job_type: str, job_id: str) -> None:
        from app.workflows.activities import (  # noqa: PLC0415
            audit_scene,
            generate_book_spec,
            generate_chapter_outline,
            generate_chapter_scene_cards,
            mark_job_status,
            polish_chapter,
            revision_rewrite_proposal,
            rewrite_scene,
            run_full_novel_pipeline,
            run_scene_writing,
        )

        await mark_job_status(job_id, "running")
        try:
            if job_type == "generate_bible":
                result = await generate_book_spec({"id": job_id})
            elif job_type == "generate_outline":
                result = await generate_chapter_outline({"id": job_id})
            elif job_type == "generate_scene_plan":
                result = await generate_chapter_scene_cards({"id": job_id})
            elif job_type == "audit_scene":
                result = await audit_scene({"id": job_id})
            elif job_type == "rewrite_scene":
                result = await rewrite_scene({"id": job_id})
            elif job_type == "polish_chapter":
                result = await polish_chapter({"id": job_id})
            elif job_type == "full_novel":
                result = await run_full_novel_pipeline({"id": job_id})
            elif job_type == "revision_rewrite_proposal":
                result = await revision_rewrite_proposal({"id": job_id})
            else:
                result = await run_scene_writing({"id": job_id})
            await mark_job_status(job_id, "succeeded", None, result)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("local_workflow_failed", extra={"job_id": job_id})
            message = str(exc) or exc.__class__.__name__
            await mark_job_status(job_id, "failed", message)


workflow_starter = WorkflowStarter()
