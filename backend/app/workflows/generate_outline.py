"""大纲生成 workflow。

仿 GenerateBibleWorkflow 的最简结构，只调一个 activity
(generate_chapter_outline)，复用 Sprint 1 已经写好的重试策略与失败时
自动释放 quota / 回滚 project.status 的链路。

Sprint 11 Phase E：主 activity 后 fire-and-forget 触发
refine_character_arcs_from_outline，让 LLM 基于 chapters 三幕结构
精细化 v0 人物 motivation/arc/secret，产出 pending 待用户审核。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        generate_chapter_outline,
        mark_job_status,
        refine_character_arcs_from_outline,
    )
    from app.workflows.retry_policy import (
        MODEL_ACTIVITY_RETRY,
        STATUS_ACTIVITY_RETRY,
    )


@workflow.defn
class GenerateOutlineWorkflow:
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
                generate_chapter_outline,
                args=[job],
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
            # Sprint 11 Phase E：fire-and-forget 人物弧光精细化。
            # activity 内部捕获所有异常并返回 dict，不影响主流程已 succeeded。
            await workflow.execute_activity(
                refine_character_arcs_from_outline,
                args=[
                    {
                        "organization_id": job.get("organization_id"),
                        "project_id": result.get("project_id") or job.get("project_id"),
                        "created_by": job.get("user_id") or job.get("created_by"),
                    }
                ],
                start_to_close_timeout=timedelta(minutes=3),
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
