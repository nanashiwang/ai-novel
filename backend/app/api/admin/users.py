from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_platform_admin
from app.repositories import UserRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class AdminUserResponse(APIModel):
    id: str
    email: str
    display_name: str
    platform_role: str
    status: str


@router.get("", response_model=list[AdminUserResponse])
async def users(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await UserRepository(db).list(limit=200)
    return rows
