from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager


class WriterService:
    async def write_scene(
        self,
        organization_id: str,
        project_id: str,
        job_id: str,
        scene_id: str,
    ) -> str:
        prompt = prompt_manager.load("writing/write_scene")
        return await model_gateway.generate_text(
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="write_scene",
            system_prompt=prompt,
            user_prompt=f"以 scene 为最小单位生成正文，scene_id={scene_id}",
            metadata={"scene_id": scene_id},
        )


writer_service = WriterService()
