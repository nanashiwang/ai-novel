from __future__ import annotations

from .common import APIModel


class GenerationJobResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    job_type: str
    status: str
    priority: str
    plan_code: str
    reserved_quota: int
    consumed_quota: int
    workflow_id: str | None = None


class ModelCallResponse(APIModel):
    id: str
    organization_id: str
    project_id: str | None
    job_id: str | None
    task_type: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    status: str
