from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.permissions import require_permission
from app.schemas.billing import PlanResponse
from app.schemas.common import APIModel
from app.services.billing.service import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(APIModel):
    plan_code: str = Field(min_length=1, max_length=64)


@router.get("/plans", response_model=list[PlanResponse])
async def plans(db: DbDep):
    rows = await billing_service.list_plans(db)
    return rows


@router.post("/checkout-session")
async def checkout_session(
    payload: CheckoutRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "billing:manage", tenant)
    return await billing_service.create_checkout_session(
        db,
        organization_id=tenant.organization_id,
        plan_code=payload.plan_code,
    )
