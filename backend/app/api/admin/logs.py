from fastapi import APIRouter
from app.api.deps import CurrentUserDep
from app.core.permissions import require_platform_admin
from app.repositories.memory_store import list_rows

router = APIRouter(tags=["admin-logs"])


@router.get("/admin/model-calls")
async def model_calls(user: CurrentUserDep) -> list[dict]:
    require_platform_admin(user)
    return list_rows("model_calls")


@router.get("/admin/audit-logs")
async def audit_logs(user: CurrentUserDep) -> list[dict]:
    require_platform_admin(user)
    return list_rows("audit_logs")
