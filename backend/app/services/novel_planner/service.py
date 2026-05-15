from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager


class NovelPlannerService:
    async def generate_story_bible(self, organization_id: str, project_id: str, job_id: str) -> dict:
        prompt = prompt_manager.load("bible/generate_story_bible")
        return await model_gateway.generate_json(
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="generate_story_bible",
            system_prompt=prompt,
            user_prompt="为项目生成故事圣经。",
            schema={"premise": "string", "theme": "string", "constraints": "array"},
            metadata={"module": "novel_planner"},
        )


novel_planner_service = NovelPlannerService()
