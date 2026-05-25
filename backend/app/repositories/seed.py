"""数据库种子脚本。

用途：首次启动或本地开发时执行 `python -m app.repositories.seed`，
注入套餐 / 套餐特性 / 演示组织与项目，使 UI 可立即看到内容。

幂等：以 `code` / `email` / `id` 为键判断，已存在则跳过。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import (
    Organization,
    OrganizationMember,
    Plan,
    PlanFeature,
    Project,
    QuotaBalance,
    User,
)
from app.models.common import new_id

PLANS = [
    {
        "code": "Free",
        "name": "Free",
        "description": "免费体验：故事圣经与短篇生成",
        "price_monthly": 0,
        "price_yearly": None,
        "currency": "CNY",
    },
    {
        "code": "Starter",
        "name": "Starter",
        "description": "适合轻量连载作者",
        "price_monthly": 49,
        "price_yearly": 490,
        "currency": "CNY",
    },
    {
        "code": "Pro",
        "name": "Pro",
        "description": "长篇小说自动生产与审稿",
        "price_monthly": 129,
        "price_yearly": 1290,
        "currency": "CNY",
    },
    {
        "code": "Team",
        "name": "Team",
        "description": "多人协作、API Key 与高级审核",
        "price_monthly": 399,
        "price_yearly": 3990,
        "currency": "CNY",
    },
    {
        "code": "Enterprise",
        "name": "Enterprise",
        "description": "专属队列、合同额度和审计导出",
        "price_monthly": 0,
        "price_yearly": None,
        "currency": "CNY",
    },
]


PLAN_FEATURES = {
    "Free": [
        {"feature_key": "monthly_generated_words", "limit_value": 50000, "limit_unit": "words"},
        {"feature_key": "monthly_review_count", "limit_value": 10, "limit_unit": "times"},
    ],
    "Starter": [
        {"feature_key": "monthly_generated_words", "limit_value": 300000, "limit_unit": "words"},
        {"feature_key": "monthly_review_count", "limit_value": 80, "limit_unit": "times"},
    ],
    "Pro": [
        {"feature_key": "monthly_generated_words", "limit_value": 1000000, "limit_unit": "words"},
        {"feature_key": "monthly_review_count", "limit_value": 300, "limit_unit": "times"},
        {"feature_key": "monthly_rewrite_count", "limit_value": 180, "limit_unit": "times"},
    ],
    "Team": [
        {"feature_key": "monthly_generated_words", "limit_value": 5000000, "limit_unit": "words"},
        {"feature_key": "monthly_review_count", "limit_value": 1500, "limit_unit": "times"},
        {"feature_key": "api_keys", "limit_value": 10, "limit_unit": "keys"},
    ],
    "Enterprise": [
        {"feature_key": "monthly_generated_words", "limit_value": 999999999, "limit_unit": "words"},
        {"feature_key": "dedicated_queue", "limit_value": 1, "limit_unit": "boolean"},
    ],
}


async def _seed_plans(session) -> None:
    for plan_data in PLANS:
        existing = await session.execute(select(Plan).where(Plan.code == plan_data["code"]))
        plan = existing.scalar_one_or_none()
        if not plan:
            plan = Plan(id=new_id("plan"), **plan_data)
            session.add(plan)
            await session.flush()
        for feat in PLAN_FEATURES.get(plan.code, []):
            existing_feat = await session.execute(
                select(PlanFeature).where(
                    PlanFeature.plan_id == plan.id,
                    PlanFeature.feature_key == feat["feature_key"],
                )
            )
            if existing_feat.scalar_one_or_none():
                continue
            session.add(
                PlanFeature(
                    id=new_id("pf"),
                    plan_id=plan.id,
                    enabled=True,
                    **feat,
                )
            )


async def _seed_demo_user(session) -> tuple[User, Organization]:
    existing = await session.execute(select(User).where(User.email == "writer@example.com"))
    writer = existing.scalar_one_or_none()
    if not writer:
        writer = User(
            id="user_writer",
            email="writer@example.com",
            password_hash=None,
            display_name="玄夜",
            status="active",
            is_platform_staff=False,
            platform_role="user",
        )
        session.add(writer)
        await session.flush()

    existing_org = await session.execute(
        select(Organization).where(Organization.id == "org_personal")
    )
    org = existing_org.scalar_one_or_none()
    if not org:
        org = Organization(
            id="org_personal",
            name="personal-workspace",
            type="personal",
            owner_user_id=writer.id,
            plan_code="Pro",
            status="active",
        )
        session.add(org)
        await session.flush()

    existing_member = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == writer.id,
        )
    )
    if not existing_member.scalar_one_or_none():
        session.add(
            OrganizationMember(
                id=new_id("mem"),
                organization_id=org.id,
                user_id=writer.id,
                role="owner",
                status="active",
            )
        )
    return writer, org


async def _seed_quota(session, organization_id: str) -> None:
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)
    seeds = [
        ("monthly_generated_words", 1_000_000, 0, 0),
        ("monthly_review_count", 300, 0, 0),
        ("monthly_rewrite_count", 180, 0, 0),
        ("concurrent_jobs", 3, 0, 0),
    ]
    for key, limit_value, used_value, reserved_value in seeds:
        existing = await session.execute(
            select(QuotaBalance).where(
                QuotaBalance.organization_id == organization_id,
                QuotaBalance.quota_key == key,
            )
        )
        if existing.scalar_one_or_none():
            continue
        session.add(
            QuotaBalance(
                id=new_id("quota"),
                organization_id=organization_id,
                quota_key=key,
                period_start=now,
                period_end=period_end,
                limit_value=limit_value,
                used_value=used_value,
                reserved_value=reserved_value,
                reset_at=period_end,
            )
        )


async def _seed_demo_project(session, organization_id: str, user_id: str) -> None:
    existing = await session.execute(select(Project).where(Project.id == "demo-project"))
    if existing.scalar_one_or_none():
        return
    session.add(
        Project(
            id="demo-project",
            organization_id=organization_id,
            created_by=user_id,
            title="雾都归档人",
            genre="悬疑 · 都市",
            target_word_count=300000,
            target_chapter_count=48,
            language="zh-CN",
            style="冷峻克制，细节密集",
            status="drafting",
        )
    )


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        await _seed_plans(session)
        writer, org = await _seed_demo_user(session)
        await _seed_quota(session, org.id)
        await _seed_demo_project(session, org.id, writer.id)
        await session.commit()
    print("[seed] 完成：plans / demo org / quota / demo project 已写入。")


if __name__ == "__main__":
    asyncio.run(seed())
