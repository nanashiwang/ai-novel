"""AI 全项目重构提案生成 workflow。"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import mark_job_status, revision_rewrite_proposal
    from app.workflows.retry_policy import MODEL_ACTIVITY_RETRY, STATUS_ACTIVITY_RETRY


@workflow.defn
class RevisionRewriteProposalWorkflow:
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
                revision_rewrite_proposal,
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
            return {"job_id": job["id"], "status": "succeeded", "result": result}
        except Exception as exc:  # noqa: BLE001
            await workflow.execute_activity(
                mark_job_status,
                args=[job["id"], "failed", str(exc)],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            raise
