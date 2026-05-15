from temporalio import workflow


@workflow.defn
class WriteChapterWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        return {"job_id": job["id"], "status": "chapter_workflow_stubbed"}
