"""全本生成 workflow。

GOAT 风格分层链路：book spec → chapter outline → scene cards → scene drafts。
真实模型调用和落库都在 activity 中完成，workflow 只负责编排。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        generate_book_spec,
        generate_chapter_outline,
        generate_scene_cards,
        mark_job_status,
        write_scene_drafts,
    )
    from app.workflows.retry_policy import (
        MODEL_ACTIVITY_RETRY,
        STATUS_ACTIVITY_RETRY,
    )


@workflow.defn
class GenerateFullNovelWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        await workflow.execute_activity(
            mark_job_status,
            args=[job["id"], "running"],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=STATUS_ACTIVITY_RETRY,
        )
        try:
            book_spec = await workflow.execute_activity(
                generate_book_spec,
                args=[job],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
            chapters = await workflow.execute_activity(
                generate_chapter_outline,
                args=[job],
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
            scenes = await workflow.execute_activity(
                generate_scene_cards,
                args=[job],
                start_to_close_timeout=timedelta(minutes=40),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
            drafts = await workflow.execute_activity(
                write_scene_drafts,
                args=[job],
                start_to_close_timeout=timedelta(hours=2),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
            result = {
                "book_spec": book_spec,
                "chapters": chapters,
                "scenes": scenes,
                "drafts": drafts,
            }
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "succeeded", None, result],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            return {"job_id": job["id"], "status": "succeeded", "result": result}
        except Exception as exc:  # noqa: BLE001
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "failed", str(exc)],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            raise
