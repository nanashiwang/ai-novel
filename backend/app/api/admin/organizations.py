from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission, require_platform_admin
from app.repositories import AuditLogRepository, OrganizationRepository, QuotaBalanceRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])


class AdminOrgResponse(APIModel):
    id: str
    name: str
    type: str
    plan_code: str
    status: str
    owner_user_id: str


class AdjustQuotaRequest(APIModel):
    quota_key: str
    delta: int
    reason: str = ""


@router.get("", response_model=list[AdminOrgResponse])
async def organizations(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await OrganizationRepository(db).list(limit=200)
    return rows


@router.patch("/{organization_id}/quota")
async def adjust_quota(
    organization_id: str,
    payload: AdjustQuotaRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "admin:quota:update")
    balance = await QuotaBalanceRepository(db).get_for_update(
        organization_id=organization_id,
        quota_key=payload.quota_key,
    )
    if not balance:
        raise NotFoundError("quota_not_found")
    before = balance.limit_value
    balance.limit_value = max(0, balance.limit_value + payload.delta)

    audit = await AuditLogRepository(db).create(
        organization_id=organization_id,
        actor_user_id=user.id,
        action="quota.manual_adjust",
        target_type="quota_balance",
        target_id=balance.id,
        before_data={"limit_value": before},
        after_data={"limit_value": balance.limit_value, "reason": payload.reason},
    )
    await db.commit()
    return {
        "status": "adjusted",
        "audit_log_id": audit.id,
        "limit_value": balance.limit_value,
    }
