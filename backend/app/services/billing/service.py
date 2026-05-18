"""套餐与计费服务。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan, PlanFeature
from app.repositories import PlanFeatureRepository, PlanRepository


class BillingService:
    async def list_plans(self, session: AsyncSession) -> list[Plan]:
        rows = await PlanRepository(session).list()
        return list(rows)

    async def list_plan_features(
        self, session: AsyncSession, *, plan_id: str
    ) -> list[PlanFeature]:
        rows = await PlanFeatureRepository(session).list(plan_id=plan_id)
        return list(rows)

    async def create_checkout_session(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        plan_code: str,
    ) -> dict:
        # 真实实现需对接 Stripe / 国内支付网关，这里先返回结构化 stub
        return {
            "status": "pending",
            "organization_id": organization_id,
            "plan_code": plan_code,
            "checkout_url": f"https://billing.example.com/checkout?org={organization_id}&plan={plan_code}",
            "message": "支付网关待对接",
        }


billing_service = BillingService()
