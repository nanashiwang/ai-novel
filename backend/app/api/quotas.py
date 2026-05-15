from fastapi import APIRouter

from app.api.deps import TenantDep
from app.repositories.memory_store import list_rows
from app.schemas.billing import QuotaBalanceResponse, UsageEventResponse
from app.services.quota.service import quota_service

router = APIRouter(tags=["quota"])


@router.get("/quotas", response_model=list[QuotaBalanceResponse])
async def quotas(tenant: TenantDep) -> list[dict]:
    return quota_service.list_balances(tenant)


@router.get("/usage", response_model=list[UsageEventResponse])
async def usage(tenant: TenantDep) -> list[dict]:
    return list_rows("usage_events", tenant.organization_id)


@router.get("/entitlements")
async def entitlements(tenant: TenantDep) -> dict:
    return {"organization_id": tenant.organization_id, "plan_code": tenant.plan_code}
