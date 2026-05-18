"""Temporal Activities。

工作流中执行的、与外部世界交互的具体步骤。activities 会被 Temporal worker 真正调度。

注意：activity 内部使用独立 SQLAlchemy session（不能复用 workflow 上下文）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from temporalio import activity

from app.core.database import AsyncSessionLocal
from app.repositories import GenerationJobRepository

_logger = logging.getLogger(__name__)


async def _with_session(handler):
    async with AsyncSessionLocal() as session:
        try:
            result = await handler(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


@activity.defn(name="mark_job_status")
async def mark_job_status(job_id: str, status: str, error_message: str | None = None) -> dict[str, Any]:
    """更新 generation_jobs 的状态、时间戳，可选 error_message。"""

    async def handler(session):
        repo = GenerationJobRepository(session)
        job = await repo.get(job_id)
        if not job:
            _logger.warning("mark_job_status: job_not_found", extra={"job_id": job_id})
            return {"updated": False}
        now = datetime.now(timezone.utc)
        job.status = status
        if status == "running" and job.started_at is None:
            job.started_at = now
        if status in {"succeeded", "failed", "cancelled"}:
            job.finished_at = now
        if error_message is not None:
            job.error_message = error_message
        return {"updated": True, "status": status}

    return await _with_session(handler)


@activity.defn(name="run_scene_writing")
async def run_scene_writing(job: dict[str, Any]) -> dict[str, Any]:
    """场景写作 activity。

    在 mock 模式下返回固定字数；real 模式下应在 worker 进程中调用 model_gateway。
    """
    target_words = int(job.get("input_payload", {}).get("target_words", 4000))
    return {"scene_id": job.get("input_payload", {}).get("scene_id"), "word_count": target_words}


@activity.defn(name="run_full_novel_pipeline")
async def run_full_novel_pipeline(job: dict[str, Any]) -> dict[str, Any]:
    """全本流水线 activity 占位。

    真实链路：规划 → 章节大纲 → 场景写作 → 审稿 → 记忆更新 → 导出。
    此处仅做骨架。
    """
    estimate_words = int(job.get("input_payload", {}).get("estimate_words", 20000))
    return {"chapters": [], "estimated_words": estimate_words}


ALL_ACTIVITIES = [mark_job_status, run_scene_writing, run_full_novel_pipeline]
