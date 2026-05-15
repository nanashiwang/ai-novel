from temporalio import workflow


@workflow.defn
class WriteSceneWorkflow:
    @workflow.run
    async def run(self, job: dict) -> dict:
        return {"job_id": job["id"], "status": "scene_workflow_stubbed"}
