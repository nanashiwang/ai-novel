from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.common import new_id
from app.models import (
    Character,
    GenerationJob,
    ModelCall,
    NovelSpec,
    PlotThread,
    Project,
    QuotaBalance,
    QuotaReservation,
    UsageEvent,
    WorldItem,
)
from app.workflows import activities


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_generate_bible_flow_persists_sprint1_records(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    token, org_id = await _register(client, "bible-flow@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)
    db_session.add(
        QuotaBalance(
            id=new_id("quota"),
            organization_id=org_id,
            quota_key="monthly_generated_words",
            period_start=now,
            period_end=now + timedelta(days=30),
            limit_value=10000,
            used_value=0,
            reserved_value=0,
            reset_at=now + timedelta(days=30),
        )
    )
    await db_session.commit()

    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "雾城记忆案",
            "genre": "悬疑幻想",
            "target_word_count": 120000,
            "target_chapter_count": 24,
            "style": "冷峻克制",
        },
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    generate_res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "记忆交易"},
    )
    assert generate_res.status_code == 202, generate_res.text
    job_id = generate_res.json()["id"]
    assert generate_res.json()["job_type"] == "generate_bible"

    for _ in range(20):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status == "succeeded":
            break
        await asyncio.sleep(0.05)

    db_session.expire_all()
    spec = (
        await db_session.execute(select(NovelSpec).where(NovelSpec.project_id == project_id))
    ).scalar_one_or_none()
    characters = (
        await db_session.execute(select(Character).where(Character.project_id == project_id))
    ).scalars().all()
    world_items = (
        await db_session.execute(select(WorldItem).where(WorldItem.project_id == project_id))
    ).scalars().all()
    plot_threads = (
        await db_session.execute(select(PlotThread).where(PlotThread.project_id == project_id))
    ).scalars().all()
    model_calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    usage_events = (
        await db_session.execute(select(UsageEvent).where(UsageEvent.job_id == job_id))
    ).scalars().all()
    reservation = (
        await db_session.execute(select(QuotaReservation).where(QuotaReservation.job_id == job_id))
    ).scalar_one_or_none()
    quota = (
        await db_session.execute(
            select(QuotaBalance).where(
                QuotaBalance.organization_id == org_id,
                QuotaBalance.quota_key == "monthly_generated_words",
            )
        )
    ).scalar_one_or_none()
    job = await db_session.get(GenerationJob, job_id)

    assert job is not None
    assert job.status == "succeeded"
    assert job.consumed_quota == 2000
    assert spec is not None
    assert spec.premise
    assert len(characters) >= 2
    assert len(world_items) >= 2
    assert len(plot_threads) >= 1
    assert len(model_calls) >= 1
    assert len(usage_events) == 1
    assert usage_events[0].amount == 2000
    assert reservation is not None
    assert reservation.status == "consumed"
    assert quota is not None
    assert quota.used_value == 2000
    assert quota.reserved_value == 0

    bible_res = await client.get(f"/api/v1/projects/{project_id}/bible", headers=headers)
    assert bible_res.status_code == 200
    bible = bible_res.json()
    assert bible["spec"]["premise"]
    assert len(bible["characters"]) >= 2
    assert len(bible["world_items"]) >= 2
    assert len(bible["plot_threads"]) >= 1
    assert bible["latest_job"]["id"] == job_id


# ---------------------------------------------------------------------------
# 失败 / 边界路径覆盖（Sprint 1 P1.6）
# ---------------------------------------------------------------------------


async def _setup_org_with_quota(
    client, db_session, *, email: str, limit_value: int = 10000
) -> tuple[str, str, dict]:
    """注册账号并预置 quota balance，返回 (org_id, project_id, auth_headers)。

    所有失败/边界测试共用同一套准备流程。
    """
    token, org_id = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)
    db_session.add(
        QuotaBalance(
            id=new_id("quota"),
            organization_id=org_id,
            quota_key="monthly_generated_words",
            period_start=now,
            period_end=now + timedelta(days=30),
            limit_value=limit_value,
            used_value=0,
            reserved_value=0,
            reset_at=now + timedelta(days=30),
        )
    )
    await db_session.commit()
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "测试项目", "target_word_count": 50000},
    )
    assert project_res.status_code == 201, project_res.text
    return org_id, project_res.json()["id"], headers


async def _await_job_terminal(db_session, job_id: str, *, max_polls: int = 30) -> GenerationJob:
    for _ in range(max_polls):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state in time")


@pytest.mark.asyncio
async def test_generate_bible_rejects_when_quota_insufficient(
    client, db_engine, db_session, monkeypatch
):
    """额度不足时应返回 402，且不创建 job/reservation。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _setup_org_with_quota(
        client, db_session, email="insufficient@example.com", limit_value=500
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000},
    )
    assert res.status_code == 402, res.text
    body = res.json()
    assert body["error"]["code"] == "quota_insufficient"

    # 失败的请求不应该留下 job 或 reservation
    db_session.expire_all()
    jobs = (await db_session.execute(select(GenerationJob))).scalars().all()
    reservations = (await db_session.execute(select(QuotaReservation))).scalars().all()
    assert jobs == []
    assert reservations == []


@pytest.mark.asyncio
async def test_generate_bible_releases_quota_and_reverts_project_on_failure(
    client, db_engine, db_session, monkeypatch
):
    """generate_book_spec 抛异常时：

    - job.status == "failed"
    - reservation.status == "released"
    - quota.reserved_value 归零
    - project.status 从 bible_generating 回退到 created
    """
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, headers = await _setup_org_with_quota(
        client, db_session, email="fail-path@example.com"
    )

    # 注入故障：让 generate_story_bible 抛异常，触发 workflow 失败路径
    from app.services.novel_planner.service import novel_planner_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_planner_failure")

    monkeypatch.setattr(novel_planner_service, "generate_story_bible", _boom)

    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "fail"},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "failed"
    assert job.consumed_quota == 0

    db_session.expire_all()
    reservation = (
        await db_session.execute(
            select(QuotaReservation).where(QuotaReservation.job_id == job_id)
        )
    ).scalar_one()
    assert reservation.status == "released"

    quota = (
        await db_session.execute(
            select(QuotaBalance).where(
                QuotaBalance.organization_id == org_id,
                QuotaBalance.quota_key == "monthly_generated_words",
            )
        )
    ).scalar_one()
    assert quota.reserved_value == 0
    assert quota.used_value == 0

    project = await db_session.get(Project, project_id)
    assert project.status == "created"


@pytest.mark.asyncio
async def test_generate_bible_reuses_existing_spec_when_force_false(
    client, db_engine, db_session, monkeypatch
):
    """已存在完整 NovelSpec 且未要求 force_regenerate 时复用，amount=0。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, headers = await _setup_org_with_quota(
        client, db_session, email="reuse@example.com"
    )

    # 预置一条完整 NovelSpec：必须同时有 premise + theme 才会触发复用分支
    db_session.add(
        NovelSpec(
            id=new_id("spec"),
            organization_id=org_id,
            project_id=project_id,
            premise="已存在的故事前提",
            theme="已存在的主题",
            genre="悬疑",
        )
    )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "force_regenerate": False},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    # 复用分支：_settle_job_usage(amount=0) → 不消耗、不写 usage_event
    assert job.consumed_quota == 0
    assert (job.output_payload or {}).get("reused") is True

    quota = (
        await db_session.execute(
            select(QuotaBalance).where(
                QuotaBalance.organization_id == org_id,
                QuotaBalance.quota_key == "monthly_generated_words",
            )
        )
    ).scalar_one()
    assert quota.used_value == 0


@pytest.mark.asyncio
async def test_get_bible_rejects_cross_tenant_access(
    client, db_engine, db_session, monkeypatch
):
    """B 组织无法访问 A 组织的 project bible：返回 404。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, _ = await _setup_org_with_quota(
        client, db_session, email="org-a@example.com"
    )
    token_b, _ = await _register(client, "org-b@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.get(f"/api/v1/projects/{project_a}/bible", headers=headers_b)
    assert res.status_code == 404, res.text

    # 同样的越权写也应该被拒
    res_write = await client.post(
        f"/api/v1/projects/{project_a}/bible/generate",
        headers=headers_b,
        json={"estimate_words": 2000},
    )
    assert res_write.status_code == 404, res_write.text
