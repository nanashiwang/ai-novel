"""额度服务。

- list_balances：返回租户所有额度记录
- reserve_quota：使用 SELECT ... FOR UPDATE 行级锁，杜绝并发超额
  · 未配置 quota_balance 时，按当前组织 plan_code 查 plan_features 取上限自动建行
  · plan_features 中无该 feature_key 或 disabled → 直接 402
- commit_quota / release_quota：在任务完成或取消时结算
- record_usage：记录使用事件
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import QuotaInsufficient
from app.core.tenancy import TenantContext
from app.models.common import new_id
from app.models.plan import Plan, PlanFeature
from app.models.quota import QuotaBalance, QuotaReservation
from app.models.usage import UsageEvent
from app.repositories import QuotaBalanceRepository, QuotaReservationRepository


async def _resolve_plan_limit(
    session: AsyncSession, plan_code: str, feature_key: str
) -> int | None:
    """从 plan_features 查找该额度对应的限额；找不到或被禁用返回 None。"""
    stmt = (
        select(PlanFeature.limit_value, PlanFeature.enabled)
        .join(Plan, Plan.id == PlanFeature.plan_id)
        .where(Plan.code == plan_code, PlanFeature.feature_key == feature_key)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    limit_value, enabled = row
    if not enabled:
        return None
    return int(limit_value) if limit_value is not None else 0


class QuotaService:
    async def list_balances(
        self,
        session: AsyncSession,
        tenant: TenantContext,
    ) -> list[QuotaBalance]:
        repo = QuotaBalanceRepository(session)
        rows = await repo.list(organization_id=tenant.organization_id)
        return list(rows)

    async def reserve_quota(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        *,
        job_id: str,
        quota_key: str,
        amount: int,
    ) -> QuotaReservation:
        if amount <= 0:
            raise QuotaInsufficient("amount_must_be_positive", code="invalid_amount")

        balance_repo = QuotaBalanceRepository(session)
        balance = await balance_repo.get_for_update(
            organization_id=tenant.organization_id,
            quota_key=quota_key,
        )
        if not balance:
            # 没有额度行：按当前组织 plan_code 查 plan_features 取真值
            limit_value = await _resolve_plan_limit(session, tenant.plan_code, quota_key)
            if limit_value is None:
                raise QuotaInsufficient(
                    "quota_not_in_plan",
                    code="quota_not_in_plan",
                    details={"plan_code": tenant.plan_code, "quota_key": quota_key},
                )
            now = datetime.now(timezone.utc)
            balance = await balance_repo.create(
                organization_id=tenant.organization_id,
                quota_key=quota_key,
                period_start=now,
                period_end=now + timedelta(days=30),
                limit_value=limit_value,
                used_value=0,
                reserved_value=0,
                reset_at=now + timedelta(days=30),
            )

        available = balance.limit_value - balance.used_value - balance.reserved_value
        if available < amount:
            raise QuotaInsufficient(
                "quota_insufficient",
                details={
                    "quota_key": quota_key,
                    "requested": amount,
                    "available": available,
                },
            )

        balance.reserved_value = balance.reserved_value + amount
        await session.flush()

        reservation = await QuotaReservationRepository(session).create(
            organization_id=tenant.organization_id,
            job_id=job_id,
            quota_key=quota_key,
            reserved_amount=amount,
            consumed_amount=0,
            status="reserved",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        return reservation

    async def commit_quota(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        *,
        reservation_id: str,
        actual_used: int | None = None,
    ) -> QuotaReservation | None:
        reservation = await QuotaReservationRepository(session).get(
            reservation_id, organization_id=tenant.organization_id
        )
        if not reservation or reservation.status != "reserved":
            return reservation

        balance = await QuotaBalanceRepository(session).get_for_update(
            organization_id=tenant.organization_id,
            quota_key=reservation.quota_key,
        )
        if not balance:
            return reservation

        used = actual_used if actual_used is not None else reservation.reserved_amount
        used = min(used, reservation.reserved_amount)
        balance.reserved_value = max(0, balance.reserved_value - reservation.reserved_amount)
        balance.used_value = balance.used_value + used
        reservation.status = "consumed"
        reservation.consumed_amount = used
        await session.flush()
        return reservation

    async def release_quota(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        *,
        reservation_id: str,
    ) -> QuotaReservation | None:
        reservation = await QuotaReservationRepository(session).get(
            reservation_id, organization_id=tenant.organization_id
        )
        if not reservation or reservation.status != "reserved":
            return reservation
        balance = await QuotaBalanceRepository(session).get_for_update(
            organization_id=tenant.organization_id,
            quota_key=reservation.quota_key,
        )
        if balance:
            balance.reserved_value = max(0, balance.reserved_value - reservation.reserved_amount)
        reservation.status = "released"
        await session.flush()
        return reservation

    async def record_usage(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        *,
        user_id: str,
        event_type: str,
        amount: int,
        unit: str,
        project_id: str | None = None,
        job_id: str | None = None,
        metadata: dict | None = None,
    ) -> UsageEvent:
        event = UsageEvent(
            id=new_id("usage"),
            organization_id=tenant.organization_id,
            user_id=user_id,
            project_id=project_id,
            job_id=job_id,
            event_type=event_type,
            amount=amount,
            unit=unit,
            event_metadata=metadata,
        )
        session.add(event)
        await session.flush()
        return event


quota_service = QuotaService()
