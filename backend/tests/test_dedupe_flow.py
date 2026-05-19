from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    GenerationJob,
    NovelSpec,
    Project,
    QuotaBalance,
)
from app.models.common import new_id
from app.workflows.starter import workflow_starter


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
        json={"title": "幂等测试", "target_word_count": 30000},
    )
    project_id = project_res.json()["id"]
    await db_session.commit()
    return org_id, project_id, headers


@pytest.mark.asyncio
async def test_duplicate_bible_request_returns_same_job(client, db_engine, db_session, monkeypatch):
    """同租户/同项目/同输入连点两次 bible/generate，第二次返回第一次的 job
    不创建新 job、不重复扣 quota。"""
    # 阻塞 mock workflow 让 job 卡在 queued 状态（不被立即推进到 succeeded）
    monkeypatch.setattr(
        workflow_starter, "_run_local", lambda *a, **kw: None
    )

    _, project_id, headers = await _setup(client, db_session, email="dedupe-bible@example.com")

    res1 = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "记忆"},
    )
    assert res1.status_code == 202, res1.text
    first_job_id = res1.json()["id"]

    res2 = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "记忆"},
    )
    assert res2.status_code == 202, res2.text
    second_job_id = res2.json()["id"]

    assert first_job_id == second_job_id, "活跃任务存在时应返回原 job_id 而非新建"

    db_session.expire_all()
    all_jobs = (
        await db_session.execute(
            select(GenerationJob).where(GenerationJob.project_id == project_id)
        )
    ).scalars().all()
    assert len(all_jobs) == 1, "仅应创建一个 job"


@pytest.mark.asyncio
async def test_different_input_creates_new_job(client, db_engine, db_session, monkeypatch):
    """输入参数变了（topic 不同）应该被视为不同请求，创建新 job。"""
    monkeypatch.setattr(
        workflow_starter, "_run_local", lambda *a, **kw: None
    )

    _, project_id, headers = await _setup(client, db_session, email="dedupe-diff@example.com")

    res1 = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "topic A"},
    )
    res2 = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "topic B"},
    )
    assert res1.json()["id"] != res2.json()["id"], "topic 不同应创建新 job"

    db_session.expire_all()
    jobs = (
        await db_session.execute(
            select(GenerationJob).where(GenerationJob.project_id == project_id)
        )
    ).scalars().all()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_dedupe_per_chapter_for_scene_plan(client, db_engine, db_session, monkeypatch):
    """generate_scene_plan 的 dedupe key 含 chapter_id，不同章节不互相吞掉。"""
    monkeypatch.setattr(
        workflow_starter, "_run_local", lambda *a, **kw: None
    )

    token, org_id = await _register(client, "dedupe-scene@example.com")
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
        json={"title": "scene dedupe"},
    )
    project_id = project_res.json()["id"]
    db_session.add(
        NovelSpec(
            id=new_id("spec"),
            organization_id=org_id,
            project_id=project_id,
            premise="测试",
            theme="测试",
        )
    )
    chap_a, chap_b = new_id("chapter"), new_id("chapter")
    for cid, idx in [(chap_a, 1), (chap_b, 2)]:
        db_session.add(
            Chapter(
                id=cid,
                organization_id=org_id,
                project_id=project_id,
                volume_id=None,
                chapter_index=idx,
                title=f"第 {idx} 章",
                summary="",
                goal="",
                conflict="",
                ending_hook="",
                status="planned",
            )
        )
    project = await db_session.get(Project, project_id)
    project.status = "outlined"
    await db_session.commit()

    # 章 A 触发场景计划
    res_a = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chap_a}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 3},
    )
    job_a = res_a.json()["id"]

    # 章 B 同参数 → 应该是独立 job（dedupe target=chapter_id 不同）
    res_b = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chap_b}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 3},
    )
    job_b = res_b.json()["id"]

    assert job_a != job_b, "不同 chapter 应该有独立 dedupe key 与独立 job"

    # 章 A 重复点 → 返回相同 job
    res_a2 = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chap_a}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 3},
    )
    assert res_a2.json()["id"] == job_a, "同 chapter 重复请求应返回原 job"
