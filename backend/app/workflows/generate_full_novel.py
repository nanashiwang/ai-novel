from temporalio import workflow


@workflow.defn
class GenerateFullNovelWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        # 真实环境按 PRD 链路拆 activity：校验、规划、scene 写作、审稿、记忆、导出、额度结算。
        return {"job_id": job["id"], "status": "workflow_stubbed"}
