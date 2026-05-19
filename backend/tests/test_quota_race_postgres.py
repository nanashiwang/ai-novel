"""真 Postgres 上的额度并发竞态测试。

验证 SELECT ... FOR UPDATE 行锁在并发场景下确实序列化。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import QuotaInsufficient
from app.core.tenancy import TenantContext
from app.models.common import new_id
from app.models.generation_job import GenerationJob
from app.models.organization import Organization, OrganizationMember
from app.models.project import Project
from app.models.quota import QuotaBalance
from app.models.user import User
from app.services.quota.service import quota_service
from tests.postgres_fixtures import pg_engine, pg_session, pg_url  # noqa: F401

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_reserve_quota_under_real_concurrency(pg_engine):
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        admin = User(id="user_x", email="x@example.com", password_hash="x", display_name="x")
        session.add(admin)
        await session.flush()
        org = Organization(
            id="org_x",
            name="x",
            type="personal",
            owner_user_id=admin.id,
            plan_code="Pro",
        )
        session.add(org)
        await session.flush()
        session.add(
            OrganizationMember(id=new_id("mem"), organization_id=org.id, user_id=admin.id, role="owner")
        )
        project = Project(
            id="project_x",
            organization_id=org.id,
            created_by=admin.id,
            title="x",
        )
        session.add(project)
        await session.flush()
        session.add_all(
            [
                GenerationJob(
                    id=f"job_{index}",
                    organization_id=org.id,
                    user_id=admin.id,
                    project_id=project.id,
                    job_type="quota_test",
                    status="queued",
                    priority="queue_pro",
                    plan_code="Pro",
                    reserved_quota=0,
                    consumed_quota=0,
                )
                for index in range(20)
            ]
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

    results = await asyncio.gather(*[reserve_once(f"job_{i}") for i in range(20)])
    success = sum(1 for r in results if r)
    # 100 / 30 → 最多 3 个成功，行锁应严格序列化
    assert success == 3, f"行锁未生效或预留逻辑错误，success={success}"
