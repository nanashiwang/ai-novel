"""Temporal Workflow Starter。

- TEMPORAL_ENABLED=false（默认）：返回 mock workflow_id，便于无依赖本地开发
- TEMPORAL_ENABLED=true：通过 temporalio 客户端启动真实 workflow

设计：starter 不直接 await client 启动结果，使用 fire-and-forget，
workflow_id 立即返回；任务状态由 worker 异步回写 generation_jobs。
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

    async def _start(self, workflow_name: str, args: list[Any], workflow_id: str) -> str:
        client = await self._get_client()
        if not client:
            return f"mock-{workflow_id}"
        try:
            await client.start_workflow(
                workflow_name,
                args=args,
                id=workflow_id,
                task_queue="novelflow-generation",
            )
            return workflow_id
        except Exception:  # noqa: BLE001
            _logger.exception("failed_to_start_workflow", extra={"workflow": workflow_name})
            return f"mock-{workflow_id}"

    def _fire_and_forget(self, workflow_name: str, job: dict, prefix: str) -> str:
        workflow_id = f"{prefix}-{job['id']}"
        if not self.settings.temporal_enabled:
            return f"mock-{workflow_id}"
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._start(workflow_name, [job], workflow_id))
            return workflow_id
        except RuntimeError:
            return f"mock-{workflow_id}"

    def start_generate_full_novel(self, job: dict) -> str:
        return self._fire_and_forget("GenerateFullNovelWorkflow", job, "generate-full-novel")

    def start_generate_bible(self, job: dict) -> str:
        return self._fire_and_forget("GenerateBibleWorkflow", job, "generate-bible")

    def start_write_scene(self, job: dict) -> str:
        return self._fire_and_forget("WriteSceneWorkflow", job, "write-scene")

    def is_mock_workflow(self, workflow_id: str | None) -> bool:
        return bool(workflow_id and workflow_id.startswith("mock-"))

    def run_local_generate_full_novel(self, job_id: str) -> None:
        self._run_local("full_novel", job_id)

    def run_local_generate_bible(self, job_id: str) -> None:
        self._run_local("generate_bible", job_id)

    def run_local_write_scene(self, job_id: str) -> None:
        self._run_local("scene_write", job_id)

    def _run_local(self, job_type: str, job_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _logger.warning("local_workflow_skipped_no_event_loop", extra={"job_id": job_id})
            return
        loop.create_task(self._execute_local(job_type, job_id))

    async def _execute_local(self, job_type: str, job_id: str) -> None:
        from app.workflows.activities import (  # noqa: PLC0415
            generate_book_spec,
            mark_job_status,
            run_full_novel_pipeline,
            run_scene_writing,
        )

        await mark_job_status(job_id, "running")
        try:
            if job_type == "generate_bible":
                result = await generate_book_spec({"id": job_id})
            elif job_type == "full_novel":
                result = await run_full_novel_pipeline({"id": job_id})
            else:
                result = await run_scene_writing({"id": job_id})
            await mark_job_status(job_id, "succeeded", None, result)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("local_workflow_failed", extra={"job_id": job_id})
            await mark_job_status(job_id, "failed", str(exc))


workflow_starter = WorkflowStarter()
