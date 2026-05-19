"""额度服务。

- list_balances：返回租户所有额度记录
- reserve_quota：使用 SELECT ... FOR UPDATE 行级锁，杜绝并发超额
  · 未配置 quota_balance 时，按当前组织 plan_code 查 plan_features 取上限自动建行
  · plan_features 中无该 feature_key 或 disabled → 直接 402
- commit_quota / release_quota：在任务完成或取消时结算
- record_usage：记录使用事件
"""
from __future__ import annotations

import asyncio
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

_SQLITE_QUOTA_LOCKS: dict[str, asyncio.Lock] = {}


def _sqlite_quota_lock(session: AsyncSession, organization_id: str) -> asyncio.Lock | None:
    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        return None
    key = organization_id
    if key not in _SQLITE_QUOTA_LOCKS:
        _SQLITE_QUOTA_LOCKS[key] = asyncio.Lock()
    return _SQLITE_QUOTA_LOCKS[key]


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
        lock = _sqlite_quota_lock(session, tenant.organization_id)
        if lock:
            async with lock:
                return await self._reserve_quota_locked(
                    session,
                    tenant,
                    job_id=job_id,
                    quota_key=quota_key,
                    amount=amount,
                )
        return await self._reserve_quota_locked(
            session,
            tenant,
            job_id=job_id,
            quota_key=quota_key,
            amount=amount,
        )

    async def _reserve_quota_locked(
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
        lock = _sqlite_quota_lock(session, tenant.organization_id)
        if lock:
            async with lock:
                return await self._commit_quota_locked(
                    session,
                    tenant,
                    reservation_id=reservation_id,
                    actual_used=actual_used,
                )
        return await self._commit_quota_locked(
            session,
            tenant,
            reservation_id=reservation_id,
            actual_used=actual_used,
        )

    async def _commit_quota_locked(
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
        # Prometheus 埋点：实际消耗的额度（commit 路径）
        if used > 0:
            from app.core.metrics import QUOTA_CONSUMED  # noqa: PLC0415

            QUOTA_CONSUMED.labels(quota_key=reservation.quota_key).inc(used)
        return reservation

    async def release_quota(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        *,
        reservation_id: str,
    ) -> QuotaReservation | None:
        lock = _sqlite_quota_lock(session, tenant.organization_id)
        if lock:
            async with lock:
                return await self._release_quota_locked(
                    session,
                    tenant,
                    reservation_id=reservation_id,
                )
        return await self._release_quota_locked(
            session,
            tenant,
            reservation_id=reservation_id,
        )

    async def _release_quota_locked(
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

    async def sync_to_plan(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        plan_code: str,
    ) -> dict[str, list[dict]]:
        """根据目标 plan 的 plan_features 重新对齐组织所有 quota_balance.limit_value。

        - 已存在的 balance：用新 plan 的 limit_value 覆盖 limit；used / reserved 保留
        - plan_features 中新增的 quota_key：新建 balance 行（初始 used=0、reserved=0）
        - plan_features 中不再启用的 quota_key：limit 改 0（不删除行，保留历史 used 便于审计）

        返回 {"updated": [...], "created": [...], "disabled": [...]}，供 audit log 使用。
        """
        # 拉当前组织所有 balance（按 quota_key 索引）
        existing_stmt = select(QuotaBalance).where(
            QuotaBalance.organization_id == organization_id
        )
        existing = {b.quota_key: b for b in (await session.execute(existing_stmt)).scalars()}

        # 拉目标 plan 的所有 enabled features
        plan_stmt = (
            select(PlanFeature.feature_key, PlanFeature.limit_value, PlanFeature.enabled)
            .join(Plan, Plan.id == PlanFeature.plan_id)
            .where(Plan.code == plan_code)
        )
        plan_features = {
            row.feature_key: (int(row.limit_value or 0), bool(row.enabled))
            for row in (await session.execute(plan_stmt)).all()
        }

        now = datetime.now(timezone.utc)
        updated: list[dict] = []
        created: list[dict] = []
        disabled: list[dict] = []

        balance_repo = QuotaBalanceRepository(session)

        for quota_key, (new_limit, enabled) in plan_features.items():
            balance = existing.get(quota_key)
            target_limit = new_limit if enabled else 0
            if balance:
                if balance.limit_value != target_limit:
                    updated.append(
                        {
                            "quota_key": quota_key,
                            "before": balance.limit_value,
                            "after": target_limit,
                        }
                    )
                    balance.limit_value = target_limit
            else:
                # 新出现的 quota：建行（period 与 reset 暂沿用 30 天滚动窗）
                await balance_repo.create(
                    organization_id=organization_id,
                    quota_key=quota_key,
                    period_start=now,
                    period_end=now + timedelta(days=30),
                    limit_value=target_limit,
                    used_value=0,
                    reserved_value=0,
                    reset_at=now + timedelta(days=30),
                )
                created.append({"quota_key": quota_key, "limit": target_limit})

        # plan 不再覆盖的 quota_key：limit 归零但保留 used / reserved 记录
        for quota_key, balance in existing.items():
            if quota_key not in plan_features and balance.limit_value != 0:
                disabled.append({"quota_key": quota_key, "before": balance.limit_value})
                balance.limit_value = 0

        await session.flush()
        return {"updated": updated, "created": created, "disabled": disabled}


quota_service = QuotaService()
