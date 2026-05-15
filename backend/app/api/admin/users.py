from fastapi import APIRouter
from app.api.deps import CurrentUserDep
from app.core.permissions import require_platform_admin
from app.repositories.memory_store import list_rows

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("")
async def users(user: CurrentUserDep) -> list[dict]:
    require_platform_admin(user)
    return [
        {"id": "user_writer", "email": "writer@example.com", "platform_role": "user", "status": "active"},
        {"id": "user_admin", "email": "admin@novelflow.ai", "platform_role": "super_admin", "status": "active"},
    ]
