"""Prompt 实验 admin API（Sprint 15-D1）。

仅平台管理员可访问；非平台 admin 调用直接 403。

API 形态：
- GET   /admin/prompt-experiments?organization_id=&status=
- POST  /admin/prompt-experiments        创建（status 默认 draft）
- PATCH /admin/prompt-experiments/{id}   更新流量比例 / variant 版本 / notes
- POST  /admin/prompt-experiments/{id}/start   draft|paused → active（设 started_at）
- POST  /admin/prompt-experiments/{id}/pause   active → paused
- POST  /admin/prompt-experiments/{id}/end     active|paused → ended（设 ended_at）
- DELETE /admin/prompt-experiments/{id}        硬删（仅 draft / ended 允许）

任何状态变更都会清空 PromptRouter 的进程内缓存，避免新策略需要等 60s 才生效。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_platform_admin
from app.models.common import new_id
from app.models.prompt_experiment import PromptExperiment
from app.repositories import PromptExperimentRepository
from app.schemas.common import APIModel
from app.services.prompt_router import prompt_router

router = APIRouter(prefix="/admin/prompt-experiments", tags=["admin-prompt-experiments"])


class PromptExperimentResponse(APIModel):
    id: str
    organization_id: str
    prompt_key: str
    variant_a_version: str
    variant_b_version: str
    traffic_split_pct: int
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    notes: str = ""
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PromptExperimentCreate(APIModel):
    organization_id: str
    prompt_key: str
    variant_a_version: str = "v1"
    variant_b_version: str = "v2"
    traffic_split_pct: int = Field(default=50, ge=0, le=100)
    notes: str = ""


class PromptExperimentUpdate(APIModel):
    variant_a_version: Optional[str] = None
    variant_b_version: Optional[str] = None
    traffic_split_pct: Optional[int] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"paused", "ended"},
    "paused": {"active", "ended"},
    "ended": set(),
}


def _to_response(exp: PromptExperiment) -> PromptExperimentResponse:
    return PromptExperimentResponse(
        id=exp.id,
        organization_id=exp.organization_id,
        prompt_key=exp.prompt_key,
        variant_a_version=exp.variant_a_version,
        variant_b_version=exp.variant_b_version,
        traffic_split_pct=exp.traffic_split_pct,
        status=exp.status,
        started_at=exp.started_at,
        ended_at=exp.ended_at,
        notes=exp.notes or "",
        created_by=exp.created_by,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
    )


@router.get("", response_model=list[PromptExperimentResponse])
async def list_experiments(
    session: DbDep,
    current_user: CurrentUserDep,
    organization_id: Optional[str] = None,
    status: Optional[Literal["draft", "active", "paused", "ended"]] = Query(default=None),
) -> list[PromptExperimentResponse]:
    require_platform_admin(current_user)
    repo = PromptExperimentRepository(session)
    rows = await repo.list(
        organization_id=organization_id,
        status=status,
        limit=200,
    )
    return [_to_response(r) for r in rows]


@router.post("", response_model=PromptExperimentResponse, status_code=201)
async def create_experiment(
    payload: PromptExperimentCreate,
    session: DbDep,
    current_user: CurrentUserDep,
) -> PromptExperimentResponse:
    require_platform_admin(current_user)
    exp = PromptExperiment(
        id=new_id("pexp"),
        organization_id=payload.organization_id,
        prompt_key=payload.prompt_key,
        variant_a_version=payload.variant_a_version,
        variant_b_version=payload.variant_b_version,
        traffic_split_pct=payload.traffic_split_pct,
        status="draft",
        notes=payload.notes,
        created_by=current_user.id,
    )
    session.add(exp)
    await session.flush()
    return _to_response(exp)


@router.patch("/{experiment_id}", response_model=PromptExperimentResponse)
async def update_experiment(
    experiment_id: str,
    payload: PromptExperimentUpdate,
    session: DbDep,
    current_user: CurrentUserDep,
) -> PromptExperimentResponse:
    require_platform_admin(current_user)
    repo = PromptExperimentRepository(session)
    exp = await repo.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="prompt_experiment_not_found")
    updates = payload.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(exp, key, value)
    await session.flush()
    prompt_router.invalidate(exp.organization_id)
    return _to_response(exp)


@router.post("/{experiment_id}/start", response_model=PromptExperimentResponse)
async def start_experiment(
    experiment_id: str,
    session: DbDep,
    current_user: CurrentUserDep,
) -> PromptExperimentResponse:
    require_platform_admin(current_user)
    return await _transition(session, experiment_id, target="active")


@router.post("/{experiment_id}/pause", response_model=PromptExperimentResponse)
async def pause_experiment(
    experiment_id: str,
    session: DbDep,
    current_user: CurrentUserDep,
) -> PromptExperimentResponse:
    require_platform_admin(current_user)
    return await _transition(session, experiment_id, target="paused")


@router.post("/{experiment_id}/end", response_model=PromptExperimentResponse)
async def end_experiment(
    experiment_id: str,
    session: DbDep,
    current_user: CurrentUserDep,
) -> PromptExperimentResponse:
    require_platform_admin(current_user)
    return await _transition(session, experiment_id, target="ended")


@router.delete("/{experiment_id}", status_code=204)
async def delete_experiment(
    experiment_id: str,
    session: DbDep,
    current_user: CurrentUserDep,
) -> None:
    require_platform_admin(current_user)
    repo = PromptExperimentRepository(session)
    exp = await repo.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="prompt_experiment_not_found")
    if exp.status not in {"draft", "ended"}:
        # active / paused 状态下不允许硬删，避免误操作丢分流证据
        raise HTTPException(
            status_code=400,
            detail="prompt_experiment_must_be_ended_before_delete",
        )
    await session.delete(exp)
    await session.flush()
    prompt_router.invalidate(exp.organization_id)


async def _transition(
    session, experiment_id: str, *, target: str
) -> PromptExperimentResponse:
    repo = PromptExperimentRepository(session)
    exp = await repo.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="prompt_experiment_not_found")
    allowed = _ALLOWED_TRANSITIONS.get(exp.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"invalid_status_transition_{exp.status}_to_{target}",
        )
    exp.status = target
    now = datetime.now(timezone.utc)
    if target == "active" and exp.started_at is None:
        exp.started_at = now
    if target == "ended":
        exp.ended_at = now
    await session.flush()
    prompt_router.invalidate(exp.organization_id)
    return _to_response(exp)
