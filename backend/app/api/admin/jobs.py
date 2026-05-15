from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.core.permissions import require_platform_admin
from app.services.generation.service import generation_service

router = APIRouter(prefix="/admin/generation-jobs", tags=["admin-generation-jobs"])


@router.get("")
async def jobs(user: CurrentUserDep) -> list[dict]:
    require_platform_admin(user)
    return generation_service.list_jobs()


@router.post("/{job_id}/cancel")
async def cancel(job_id: str, user: CurrentUserDep) -> dict:
    require_platform_admin(user)
    return {"job_id": job_id, "status": "cancel_requested", "actor": user.id}
