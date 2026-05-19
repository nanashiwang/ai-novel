from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    GenerationJob,
    ModelCall,
    NovelSpec,
    Project,
    QuotaBalance,
    QuotaReservation,
    UsageEvent,
)
from app.models.common import new_id
from app.workflows import activities


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


async def _setup_org_project_and_spec(
    client,
    db_session,
    *,
    email: str,
    limit_value: int = 10000,
    with_spec: bool = True,
) -> tuple[str, str, dict]:
    """通用准备流程。

    1. 注册账号 → 返回 (org_id, project_id, headers)
    2. 预置 QuotaBalance 让 outline 端点能预留额度
    3. with_spec=True 时直接在 db 写入一条完整 NovelSpec（绕过 bible 流程）。
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
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "雾城记忆案", "target_chapter_count": 6, "target_word_count": 60000},
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]
    if with_spec:
        # 模拟 bible 已生成的状态
        project = await db_session.get(Project, project_id)
        project.status = "bible_ready"
        db_session.add(
            NovelSpec(
                id=new_id("spec"),
                organization_id=org_id,
                project_id=project_id,
                premise="一个测试前提",
                theme="测试主题",
                genre="测试",
            )
        )
    await db_session.commit()
    return org_id, project_id, headers


async def _await_job_terminal(db_session, job_id: str, *, max_polls: int = 30) -> GenerationJob:
    for _ in range(max_polls):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state in time")


@pytest.mark.asyncio
async def test_generate_outline_happy_path(client, db_engine, db_session, monkeypatch):
    """有 bible → 生成 outline → chapters 落库 → project.status=outlined → quota 消耗。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, headers = await _setup_org_project_and_spec(
        client, db_session, email="outline-happy@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/outline/generate",
        headers=headers,
        json={"target_chapters": 4, "estimate_words": 3000},
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["job_type"] == "generate_outline"
    job_id = body["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.consumed_quota == 3000

    db_session.expire_all()
    chapters = (
        await db_session.execute(select(Chapter).where(Chapter.project_id == project_id))
    ).scalars().all()
    assert len(chapters) == 4
    for ch in chapters:
        assert ch.title
        assert ch.summary
        assert ch.goal
        assert ch.conflict
        assert ch.ending_hook
    indices = sorted(c.chapter_index for c in chapters)
    assert indices == [1, 2, 3, 4]

    model_calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    assert len(model_calls) >= 1
    assert all(mc.prompt_key == "outline/plan_chapters" for mc in model_calls)

    usage = (
        await db_session.execute(select(UsageEvent).where(UsageEvent.job_id == job_id))
    ).scalar_one()
    assert usage.amount == 3000

    reservation = (
        await db_session.execute(
            select(QuotaReservation).where(QuotaReservation.job_id == job_id)
        )
    ).scalar_one()
    assert reservation.status == "consumed"

    project = await db_session.get(Project, project_id)
    assert project.status == "outlined"


@pytest.mark.asyncio
async def test_generate_outline_rejects_without_bible(client, db_engine, db_session, monkeypatch):
    """没有 NovelSpec 时拒绝，返回 404 novel_spec_not_found。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _setup_org_project_and_spec(
        client, db_session, email="outline-nobible@example.com", with_spec=False
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/outline/generate",
        headers=headers,
        json={"target_chapters": 4},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "novel_spec_not_found"

    # 拒绝路径不应该创建 job 或 reservation
    db_session.expire_all()
    assert (await db_session.execute(select(GenerationJob))).scalars().all() == []
    assert (await db_session.execute(select(QuotaReservation))).scalars().all() == []


@pytest.mark.asyncio
async def test_generate_outline_releases_quota_and_reverts_status_on_failure(
    client, db_engine, db_session, monkeypatch
):
    """plan_chapters 抛异常时：

    - job.status == "failed"
    - reservation.status == "released"
    - QuotaBalance.reserved_value 归零
    - project.status 从 outline_generating 回退到 bible_ready
    """
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, headers = await _setup_org_project_and_spec(
        client, db_session, email="outline-fail@example.com"
    )

    from app.services.novel_planner.service import novel_planner_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_planner_failure")

    monkeypatch.setattr(novel_planner_service, "plan_chapters", _boom)

    res = await client.post(
        f"/api/v1/projects/{project_id}/outline/generate",
        headers=headers,
        json={"target_chapters": 4},
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
    assert project.status == "bible_ready"


@pytest.mark.asyncio
async def test_generate_outline_reuses_existing_chapters_when_force_false(
    client, db_engine, db_session, monkeypatch
):
    """已有 chapters 且 force_regenerate=false 时走 reuse 分支，不再扣额度。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, headers = await _setup_org_project_and_spec(
        client, db_session, email="outline-reuse@example.com"
    )

    # 预置两章 chapters，触发 reuse 分支
    for idx in range(1, 3):
        db_session.add(
            Chapter(
                id=new_id("chapter"),
                organization_id=org_id,
                project_id=project_id,
                volume_id=None,
                chapter_index=idx,
                title=f"已存在的第{idx}章",
                summary="预置摘要",
                goal="预置目标",
                conflict="预置冲突",
                ending_hook="预置钩子",
                status="planned",
            )
        )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/outline/generate",
        headers=headers,
        json={"target_chapters": 5, "force_regenerate": False},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.consumed_quota == 0
    assert (job.output_payload or {}).get("reused") is True
    assert (job.output_payload or {}).get("chapter_count") == 2

    db_session.expire_all()
    quota = (
        await db_session.execute(
            select(QuotaBalance).where(
                QuotaBalance.organization_id == org_id,
                QuotaBalance.quota_key == "monthly_generated_words",
            )
        )
    ).scalar_one()
    assert quota.used_value == 0
    assert quota.reserved_value == 0


@pytest.mark.asyncio
async def test_generate_outline_rejects_cross_tenant(client, db_engine, db_session, monkeypatch):
    """org B 不能触发 org A 项目的 outline，返回 404。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, _ = await _setup_org_project_and_spec(
        client, db_session, email="outline-a@example.com"
    )
    token_b, _ = await _register(client, "outline-b@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.post(
        f"/api/v1/projects/{project_a}/outline/generate",
        headers=headers_b,
        json={"target_chapters": 4},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "project_not_found"
