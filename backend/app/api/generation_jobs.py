from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, TenantDep
from app.schemas.generation import GenerationJobResponse
from app.services.generation.service import generation_service

router = APIRouter(prefix="/generation-jobs", tags=["generation-jobs"])


@router.get("/{job_id}", response_model=GenerationJobResponse)
async def get_job(job_id: str, tenant: TenantDep) -> dict:
    job = generation_service.get_job(tenant, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return job


@router.post("/{job_id}/cancel", response_model=GenerationJobResponse)
async def cancel_job(job_id: str, tenant: TenantDep, user: CurrentUserDep) -> dict:
    job = generation_service.cancel_job(user, tenant, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return job
