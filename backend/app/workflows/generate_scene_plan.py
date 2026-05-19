"""场景计划生成 workflow。

单章模式：input_payload 必须包含 chapter_id。仅为该章拆出 scene cards
（3-8 个，受 input_payload.scenes_per_chapter 影响），不影响其他章。
与项目级的 generate_scene_cards activity 区分：后者用于 full_novel pipeline
遍历所有 chapters。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import generate_chapter_scene_cards, mark_job_status
    from app.workflows.retry_policy import (
        MODEL_ACTIVITY_RETRY,
        STATUS_ACTIVITY_RETRY,
    )


@workflow.defn
class GenerateScenePlanWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        await workflow.execute_activity(
            mark_job_status,
            args=[job["id"], "running"],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=STATUS_ACTIVITY_RETRY,
        )
        try:
            result = await workflow.execute_activity(
                generate_chapter_scene_cards,
                args=[job],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
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
