"""故事圣经生成 workflow。"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import generate_book_spec, mark_job_status


@workflow.defn
class GenerateBibleWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        await workflow.execute_activity(
            mark_job_status,
            args=[job["id"], "running"],
            start_to_close_timeout=timedelta(minutes=1),
        )
        try:
            result = await workflow.execute_activity(
                generate_book_spec,
                args=[job],
                start_to_close_timeout=timedelta(minutes=10),
            )
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "succeeded", None, result],
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

