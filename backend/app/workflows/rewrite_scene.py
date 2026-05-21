"""场景重写 workflow。

单 activity 任务：调 rewrite_scene，基于当前 open issues 重写 draft，新建
version_type=rewrite 的 DraftVersion，把 issues 标 fixed。Sprint 5-A。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        extract_plot_thread_changes_from_scene,
        extract_world_changes_from_scene,
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
                mark_job_status,
                args=[job["id"], "succeeded", None, result],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            # Sprint 12-C: fire-and-forget — 主流程已成功；下列 activity 失败也
            # 不应让 workflow 报错。activity 自身把异常吞掉，这里仅控制 timeout。
            scene_id = (result or {}).get("scene_id")
            if scene_id:
                fan_out_payload = {"scene_id": scene_id, "job_id": job["id"]}
                try:
                    await workflow.execute_activity(
                        extract_world_changes_from_scene,
                        args=[fan_out_payload],
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=STATUS_ACTIVITY_RETRY,
                    )
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await workflow.execute_activity(
                        extract_plot_thread_changes_from_scene,
                        args=[fan_out_payload],
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=STATUS_ACTIVITY_RETRY,
                    )
                except Exception:  # noqa: BLE001
                    pass
            return {"job_id": job["id"], "status": "succeeded", "result": result}
        except Exception as exc:  # noqa: BLE001
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "failed", str(exc)],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            raise
