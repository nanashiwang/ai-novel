from __future__ import annotations

import time
from typing import Any

from app.core.config import get_settings
from app.repositories.memory_store import insert_row


class ModelGateway:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate_json(
        self,
        organization_id: str,
        project_id: str | None,
        job_id: str | None,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        response_json = {
            "mock": True,
            "task_type": task_type,
            "schema_keys": list(schema.keys()),
            "metadata": metadata or {},
        }
        self._record_call(
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_json=response_json,
            response_text=None,
            started=started,
        )
        return response_json

    async def generate_text(
        self,
        organization_id: str,
        project_id: str | None,
        job_id: str | None,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        started = time.perf_counter()
        response_text = f"[MOCK:{task_type}] 已根据上下文生成 scene 级正文。"
        self._record_call(
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_json=None,
            response_text=response_text,
            started=started,
        )
        return response_text

    def _record_call(
        self,
        organization_id: str,
        project_id: str | None,
        job_id: str | None,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        response_json: dict[str, Any] | None,
        response_text: str | None,
        started: float,
    ) -> None:
        input_tokens = max(1, (len(system_prompt) + len(user_prompt)) // 4)
        output_tokens = max(1, len(response_text or str(response_json)) // 4)
        insert_row(
            "model_calls",
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "job_id": job_id,
                "task_type": task_type,
                "model": self.settings.default_model,
                "prompt_key": task_type,
                "prompt_version": "v1",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_text": response_text,
                "response_json": response_json,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "status": "success",
            },
            "model_call",
        )


model_gateway = ModelGateway()
