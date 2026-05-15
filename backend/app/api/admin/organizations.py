from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.core.permissions import require_permission, require_platform_admin
from app.repositories.memory_store import insert_row

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])


@router.get("")
async def organizations(user: CurrentUserDep) -> list[dict]:
    require_platform_admin(user)
    return [
        {
            "id": "org_personal",
            "name": "personal-workspace",
            "plan_code": "Pro",
            "status": "active",
        }
    ]


@router.patch("/{organization_id}/quota")
async def adjust_quota(organization_id: str, user: CurrentUserDep) -> dict:
    require_permission(user, "admin:quota:update")
    audit = insert_row(
        "admin_audit_logs",
        {
            "organization_id": organization_id,
            "actor_user_id": user.id,
            "action": "quota.manual_adjust",
            "target_type": "quota_balance",
            "target_id": organization_id,
        },
        "audit",
    )
    return {"status": "mock_adjusted", "audit_log_id": audit["id"]}
