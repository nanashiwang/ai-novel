from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.core.permissions import require_platform_admin

router = APIRouter(prefix="/admin/content-reviews", tags=["admin-content-reviews"])


@router.get("")
async def content_reviews(user: CurrentUserDep) -> list[dict]:
    require_platform_admin(user)
    return [
        {"id": "review_1", "risk": "medium", "status": "pending", "title": "Prompt 内容待复核"}
    ]
