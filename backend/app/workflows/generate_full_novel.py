"""全本生成 workflow。

链路：标记 running → 跑流水线 → 标记 succeeded（失败标记 failed）。
真实生产应拆为更多 activity：bible / outline / chapter / scene / audit / export。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        mark_job_status,
        run_full_novel_pipeline,
    )


@workflow.defn
class GenerateFullNovelWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        await workflow.execute_activity(
            mark_job_status,
            args=[job["id"], "running"],
            start_to_close_timeout=timedelta(minutes=1),
        )
        try:
            result = await workflow.execute_activity(
                run_full_novel_pipeline,
                args=[job],
                start_to_close_timeout=timedelta(hours=2),
            )
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "succeeded"],
                start_to_close_timeout=timedelta(minutes=1),
            )
            return {"job_id": job["id"], "status": "succeeded", "result": result}
        except Exception as exc:  # noqa: BLE001
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "failed", str(exc)],
                start_to_close_timeout=timedelta(minutes=1),
            )
            raise
