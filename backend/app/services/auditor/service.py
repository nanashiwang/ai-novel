from app.services.model_gateway.service import model_gateway


class AuditorService:
    async def audit_scene(
        self,
        organization_id: str,
        project_id: str,
        job_id: str,
        scene_text: str,
    ) -> dict:
        return await model_gateway.generate_json(
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="audit_scene",
            system_prompt="检查连续性、人物动机、世界观硬规则和文风一致性。",
            user_prompt=scene_text,
            schema={"issues": "array"},
            metadata={"module": "auditor"},
        )


auditor_service = AuditorService()
