"""场景重写 workflow。

单 activity 任务：调 rewrite_scene，基于当前 open issues 重写 draft，新建
version_type=rewrite 的 DraftVersion，把 issues 标 fixed。Sprint 5-A。

Sprint 10 Phase B：rewrite 主 activity 后追加 fire-and-forget 角色推演。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        extract_character_state_from_scene,
        mark_job_status,
        rewrite_scene,
    )
    from app.workflows.retry_policy import (
        MODEL_ACTIVITY_RETRY,
        STATUS_ACTIVITY_RETRY,
    )


@workflow.defn
class RewriteSceneWorkflow:
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
                rewrite_scene,
                args=[job],
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
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
