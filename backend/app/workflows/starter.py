from app.core.config import get_settings


class WorkflowStarter:
    def start_generate_full_novel(self, job: dict) -> str:
        if get_settings().environment == "local":
            return f"mock-generate-full-novel-{job['id']}"
        return f"temporal-generate-full-novel-{job['id']}"

    def start_write_scene(self, job: dict) -> str:
        if get_settings().environment == "local":
            return f"mock-write-scene-{job['id']}"
        return f"temporal-write-scene-{job['id']}"


workflow_starter = WorkflowStarter()
