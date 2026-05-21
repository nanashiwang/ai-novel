"""场景写作 workflow。"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        extract_character_state_from_scene,
        mark_job_status,
        run_scene_writing,
    )
    from app.workflows.retry_policy import (
        MODEL_ACTIVITY_RETRY,
        STATUS_ACTIVITY_RETRY,
    )


@workflow.defn
class WriteSceneWorkflow:
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
                run_scene_writing,
                args=[job],
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
            # Sprint 10 Phase B：fire-and-forget 推演角色状态变化。
            # activity 内部已捕获所有异常并返回 dict，绝不抛出，
            # 不会影响 succeeded 标记。
            await workflow.execute_activity(
                extract_character_state_from_scene,
                args=[
                    {
                        "organization_id": job.get("organization_id"),
                        "project_id": result.get("project_id") or job.get("project_id"),
                        "scene_id": result["scene_id"],
                        "draft_id": result["draft_id"],
                        "created_by": job.get("user_id") or job.get("created_by"),
                    }
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "succeeded"],
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
