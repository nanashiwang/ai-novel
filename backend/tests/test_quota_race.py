"""额度并发竞态测试。

模拟同一个组织同时发起多次额度预留，断言不会超额：
- 总额 100，每次扣 30
- 10 个并发请求中只能有 ≤ 3 个成功
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import QuotaInsufficient
from app.core.tenancy import TenantContext
from app.models.common import new_id
from app.models.organization import Organization, OrganizationMember
from app.models.quota import QuotaBalance
from app.models.user import User
from app.services.quota.service import quota_service


@pytest.mark.asyncio
async def test_reserve_quota_does_not_overcommit(db_engine):
    Session = async_sessionmaker(db_engine, expire_on_commit=False)

    async with Session() as session:
        admin = User(
            id="user_admin",
            email="x@example.com",
            password_hash="x",
            display_name="x",
        )
        session.add(admin)
        org = Organization(
            id="org_x",
            name="x",
            type="personal",
            owner_user_id=admin.id,
            plan_code="Pro",
        )
        session.add(org)
        session.add(
            OrganizationMember(
                id=new_id("mem"), organization_id=org.id, user_id=admin.id, role="owner"
            )
        )
        now = datetime.now(timezone.utc)
        session.add(
            QuotaBalance(
                id=new_id("quota"),
                organization_id=org.id,
                quota_key="monthly_generated_words",
                period_start=now,
                period_end=now + timedelta(days=30),
                limit_value=100,
                used_value=0,
                reserved_value=0,
                reset_at=now + timedelta(days=30),
            )
        )
        await session.commit()

    tenant = TenantContext(
        organization_id="org_x",
        organization_name="x",
        plan_code="Pro",
        organization_role="owner",
    )

    async def reserve_once(job_id: str) -> bool:
        async with Session() as s:
            try:
                await quota_service.reserve_quota(
                    s, tenant, job_id=job_id, quota_key="monthly_generated_words", amount=30
                )
                await s.commit()
                return True
            except QuotaInsufficient:
                await s.rollback()
                return False

    results = await asyncio.gather(*[reserve_once(f"job_{i}") for i in range(10)])
    success = sum(1 for r in results if r)
    # 总额 100、单次 30 → 最多 3 个成功
    assert success <= 3, f"超额：{success} 次成功"


@pytest.mark.asyncio
async def test_reserve_quota_zero_amount_rejected(db_session):
    tenant = TenantContext(
        organization_id="org_y",
        organization_name="y",
        plan_code="Pro",
        organization_role="owner",
    )
    with pytest.raises(QuotaInsufficient):
        await quota_service.reserve_quota(
            db_session,
            tenant,
            job_id="job_y",
            quota_key="monthly_generated_words",
            amount=0,
        )
