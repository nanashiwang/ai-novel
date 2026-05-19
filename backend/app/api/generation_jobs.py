from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.schemas.generation import GenerationJobResponse
from app.services.generation.service import generation_service

router = APIRouter(prefix="/generation-jobs", tags=["generation-jobs"])


@router.get("", response_model=list[GenerationJobResponse])
async def list_jobs(tenant: TenantDep, db: DbDep):
    rows = await generation_service.list_jobs(db, tenant)
    return rows


@router.get("/{job_id}", response_model=GenerationJobResponse)
async def get_job(job_id: str, tenant: TenantDep, db: DbDep):
    job = await generation_service.get_job(db, tenant, job_id)
    if not job:
        raise NotFoundError("job_not_found")
    return job


@router.post("/{job_id}/cancel", response_model=GenerationJobResponse)
async def cancel_job(job_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    job = await generation_service.cancel_job(db, user, tenant, job_id)
    if not job:
        raise NotFoundError("job_not_found")
    await db.commit()
    return job


@router.post("/{job_id}/retry", response_model=GenerationJobResponse, status_code=202)
async def retry_job(job_id: str, tenant: TenantDep, user: CurrentUserDep, db: DbDep):
    """重试已失败/已取消的任务。

    Sprint 6-A：根据原 job 的 job_type 与 input_payload 创建一个新 job，
    通过 input_payload.retry_of 保留溯源；原 job 行保持不动以供审计。
    """
    job = await generation_service.get_job(db, tenant, job_id)
    if not job:
        raise NotFoundError("job_not_found")
    new_job = await generation_service.retry_job(db, user, tenant, job=job)
    await db.refresh(new_job)
    response = GenerationJobResponse.model_validate(new_job)
    await db.commit()
    return response
