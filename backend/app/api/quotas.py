from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep, TenantDep
from app.repositories import UsageEventRepository
from app.schemas.billing import QuotaBalanceResponse, UsageEventResponse
from app.services.entitlement.service import PLAN_ENTITLEMENTS
from app.services.quota.service import quota_service

router = APIRouter(tags=["quota"])


@router.get("/quotas", response_model=list[QuotaBalanceResponse])
async def quotas(tenant: TenantDep, db: DbDep):
    balances = await quota_service.list_balances(db, tenant)
    return balances


@router.get("/usage", response_model=list[UsageEventResponse])
async def usage(tenant: TenantDep, db: DbDep):
    rows = await UsageEventRepository(db).list(organization_id=tenant.organization_id, limit=200)
    return rows


@router.get("/entitlements")
async def entitlements(tenant: TenantDep):
    entitlements_for_plan = list(PLAN_ENTITLEMENTS.get(tenant.plan_code, set()))
    return {
        "organization_id": tenant.organization_id,
        "plan_code": tenant.plan_code,
        "entitlements": entitlements_for_plan,
    }
