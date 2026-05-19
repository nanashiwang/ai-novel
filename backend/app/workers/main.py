"""Temporal Worker 主入口。

启动命令：`python -m app.workers.main`
环境变量：
  TEMPORAL_ENABLED=true 否则直接退出
  TEMPORAL_HOST、TEMPORAL_NAMESPACE 同 web 端配置
"""
from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workflows.activities import ALL_ACTIVITIES
from app.workflows.audit_scene import AuditSceneWorkflow
from app.workflows.generate_bible import GenerateBibleWorkflow
from app.workflows.generate_full_novel import GenerateFullNovelWorkflow
from app.workflows.generate_outline import GenerateOutlineWorkflow
from app.workflows.generate_scene_plan import GenerateScenePlanWorkflow
from app.workflows.rewrite_scene import RewriteSceneWorkflow
from app.workflows.write_scene import WriteSceneWorkflow

_logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.temporal_enabled:
        _logger.warning("TEMPORAL_ENABLED=false，worker 未启动；如需运行 worker 请打开开关。")
        return

    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        _logger.error("temporalio 未安装，无法启动 worker")
        sys.exit(1)

    client = await Client.connect(
        settings.temporal_host, namespace=settings.temporal_namespace
    )
    worker = Worker(
        client,
        task_queue="novelflow-generation",
        workflows=[
            AuditSceneWorkflow,
            GenerateBibleWorkflow,
            GenerateFullNovelWorkflow,
            GenerateOutlineWorkflow,
            GenerateScenePlanWorkflow,
            RewriteSceneWorkflow,
            WriteSceneWorkflow,
        ],
        activities=ALL_ACTIVITIES,
    )
    _logger.info("temporal_worker_started", extra={"task_queue": "novelflow-generation"})
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
