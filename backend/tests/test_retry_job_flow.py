from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import GenerationJob, Organization, Project, QuotaBalance
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


async def _setup(client, db_session, *, email: str) -> tuple[str, str, dict]:
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
            limit_value=10000,
            used_value=0,
            reserved_value=0,
            reset_at=now + timedelta(days=30),
        )
    )
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "retry 测试", "target_word_count": 50000},
    )
    project_id = project_res.json()["id"]
    await db_session.commit()
    return org_id, project_id, headers


async def _await_terminal(db_session, job_id: str, *, max_polls: int = 30) -> GenerationJob:
    for _ in range(max_polls):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state")


@pytest.mark.asyncio
async def test_retry_failed_job_creates_new_job_with_retry_of(
    client, db_engine, db_session, monkeypatch
):
    """failed 任务 retry → 新 job + input_payload.retry_of=old_job_id。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _setup(client, db_session, email="retry-failed@example.com")

    # mock 失败：让 novel_planner 抛异常
    from app.services.novel_planner.service import novel_planner_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_failure")

    monkeypatch.setattr(novel_planner_service, "generate_story_bible", _boom)

    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "原 topic"},
    )
    assert res.status_code == 202, res.text
    old_job_id = res.json()["id"]
    old_job = await _await_terminal(db_session, old_job_id)
    assert old_job.status == "failed"

    # 解除失败注入，让 retry 真的能跑通
    monkeypatch.undo()

    # retry
    retry_res = await client.post(
        f"/api/v1/generation-jobs/{old_job_id}/retry",
        headers=headers,
    )
    assert retry_res.status_code == 202, retry_res.text
    new_job_id = retry_res.json()["id"]
    assert new_job_id != old_job_id
    assert retry_res.json()["job_type"] == "generate_bible"

    db_session.expire_all()
    new_job = await db_session.get(GenerationJob, new_job_id)
    assert new_job is not None
    assert (new_job.input_payload or {}).get("retry_of") == old_job_id
    assert (new_job.input_payload or {}).get("topic") == "原 topic"

    # 原 job 不应被改动
    old_after = await db_session.get(GenerationJob, old_job_id)
    assert old_after.status == "failed"


@pytest.mark.asyncio
async def test_retry_rejects_succeeded_job(client, db_engine, db_session, monkeypatch):
    """succeeded 任务不能 retry → 409 job_not_retryable。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _setup(client, db_session, email="retry-succ@example.com")

    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000},
    )
    assert res.status_code == 202
    job_id = res.json()["id"]
    job = await _await_terminal(db_session, job_id)
    assert job.status == "succeeded"

    retry_res = await client.post(
        f"/api/v1/generation-jobs/{job_id}/retry",
        headers=headers,
    )
    assert retry_res.status_code == 409, retry_res.text
    assert retry_res.json()["error"]["code"] == "conflict"


@pytest.mark.asyncio
async def test_retry_rejects_cross_tenant(client, db_engine, db_session, monkeypatch):
    """org B 不能 retry org A 的 job → 404。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, headers_a = await _setup(client, db_session, email="retry-org-a@example.com")
    res = await client.post(
        f"/api/v1/projects/{project_a}/bible/generate",
        headers=headers_a,
        json={"estimate_words": 2000},
    )
    job_id = res.json()["id"]
    await _await_terminal(db_session, job_id)

    token_b, _ = await _register(client, "retry-org-b@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    res_b = await client.post(
        f"/api/v1/generation-jobs/{job_id}/retry",
        headers=headers_b,
    )
    assert res_b.status_code == 404, res_b.text
