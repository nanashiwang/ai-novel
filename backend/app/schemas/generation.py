from __future__ import annotations

from datetime import datetime
from typing import Any

from .common import APIModel


class GenerationJobResponse(APIModel):
    id: str
    organization_id: str
    user_id: str
    project_id: str
    job_type: str
    status: str
    priority: str
    plan_code: str
    reserved_quota: int
    consumed_quota: int
    workflow_id: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # 用户提交时的参数（chapter_id / topic / scenes_per_chapter 等），
    # 前端用于按章节区分 scene_plan 任务等场景。仅含用户输入字段，
    # 不包含敏感配置。
    input_payload: dict[str, Any] | None = None
    # activity 执行后写回的结果（scene_id / draft_id / context_summary 等）。
    # 用于 Sprint 4-B2 的 ContextBuilder Inspector 等"看任务做了什么"的视图。
    output_payload: dict[str, Any] | None = None


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
    created_at: datetime
