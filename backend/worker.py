"""Temporal worker 入口。

注册本仓库的全部 workflow / activity，监听 `novelflow-generation`
task_queue。生产环境作为独立进程运行（与 API 进程同代码、不同 entrypoint）。

启动：
    cd backend
    TEMPORAL_ENABLED=true .venv/bin/python worker.py

详细部署步骤见 docs/temporal_worker_deployment.md。
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.workflows.activities import (
    audit_scene,
    generate_book_spec,
    generate_chapter_outline,
    generate_chapter_scene_cards,
    mark_job_status,
    rewrite_scene,
    run_full_novel_pipeline,
    run_scene_writing,
)
from app.workflows.audit_scene import AuditSceneWorkflow
from app.workflows.generate_bible import GenerateBibleWorkflow
from app.workflows.generate_full_novel import GenerateFullNovelWorkflow
from app.workflows.generate_outline import GenerateOutlineWorkflow
from app.workflows.generate_scene_plan import GenerateScenePlanWorkflow
from app.workflows.rewrite_scene import RewriteSceneWorkflow
from app.workflows.write_scene import WriteSceneWorkflow

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("novelflow.worker")


async def main() -> None:
    settings = get_settings()
    if not settings.temporal_enabled:
        _logger.warning(
            "TEMPORAL_ENABLED=false; worker 仍会连接 %s 但 API 进程不会派发任务",
            settings.temporal_host,
        )

    # 延迟 import 避免在 TEMPORAL_ENABLED=false 的开发环境强依赖 temporalio
    from temporalio.client import Client  # noqa: PLC0415
    from temporalio.worker import Worker  # noqa: PLC0415

    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue="novelflow-generation",
        workflows=[
            GenerateBibleWorkflow,
            GenerateOutlineWorkflow,
            GenerateScenePlanWorkflow,
            WriteSceneWorkflow,
            AuditSceneWorkflow,
            RewriteSceneWorkflow,
            GenerateFullNovelWorkflow,
        ],
        activities=[
            mark_job_status,
            generate_book_spec,
            generate_chapter_outline,
            generate_chapter_scene_cards,
            run_scene_writing,
            audit_scene,
            rewrite_scene,
            run_full_novel_pipeline,
        ],
        max_concurrent_activities=8,
    )
    _logger.info("worker_started host=%s namespace=%s", settings.temporal_host, settings.temporal_namespace)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
