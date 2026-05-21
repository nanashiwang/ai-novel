from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    Character,
    DraftVersion,
    GenerationJob,
    MemoryEntry,
    ModelCall,
    NovelSpec,
    Organization,
    Project,
    QuotaBalance,
    QuotaReservation,
    Scene,
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


async def _setup_org_project_spec_scene(
    client,
    db_session,
    *,
    email: str,
    limit_value: int = 10000,
    with_scene: bool = True,
) -> tuple[str, str, str, str, dict]:
    """注册 + quota + project + NovelSpec + 1 章 + 1 scene。

    返回 (org_id, project_id, chapter_id, scene_id, headers)。
    with_scene=False 时跳过 scene 创建（用于测试 scene_not_found）。
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
        json={"title": "写作测试项目", "target_chapter_count": 3, "target_word_count": 30000},
    )
    project_id = project_res.json()["id"]
    chapter_id = new_id("chapter")
    scene_id = new_id("scene") if with_scene else ""
    db_session.add(
        NovelSpec(
            id=new_id("spec"),
            organization_id=org_id,
            project_id=project_id,
            premise="测试前提",
            theme="测试主题",
            genre="奇幻",
        )
    )
    db_session.add(
        Chapter(
            id=chapter_id,
            organization_id=org_id,
            project_id=project_id,
            volume_id=None,
            chapter_index=1,
            title="第一章",
            summary="开局摘要",
            goal="建立世界观",
            conflict="主角面对未知",
            ending_hook="留下悬念",
            status="planned",
        )
    )
    if with_scene:
        db_session.add(
            Scene(
                id=scene_id,
                organization_id=org_id,
                project_id=project_id,
                chapter_id=chapter_id,
                scene_index=1,
                title="开场场景",
                time_marker="清晨",
                location="档案馆",
                characters=["林澈"],
                goal="进入档案室",
                conflict="门禁失效",
                emotion_start="平静",
                emotion_end="警觉",
                reveal="档案被人篡改",
                hook="找到陌生符号",
                status="planned",
            )
        )
    db_session.add(
        Character(
            id=new_id("char"),
            organization_id=org_id,
            project_id=project_id,
            name="林澈",
            role="protagonist",
            description="旧城区档案员，能读取旧物记忆。",
            personality="克制敏锐，习惯独自承担风险。",
            motivation="追查妹妹失踪案。",
            secret="曾接触过核心记忆样本。",
            arc="从逃避真相到主动揭开城市记忆系统。",
            relationships={},
            current_state={"status": "准备进入档案馆"},
        )
    )
    project = await db_session.get(Project, project_id)
    project.status = "scenes_planned"
    # 升级到 Pro plan：write_scene 端点要求 entitlement "generation:scene"，
    # Free plan 默认没有；测试中显式升级避免 setup 与计费模型耦合。
    org_row = await db_session.get(Organization, org_id)
    org_row.plan_code = "Pro"
    await db_session.commit()
    return org_id, project_id, chapter_id, scene_id, headers


async def _await_job_terminal(db_session, job_id: str, *, max_polls: int = 30) -> GenerationJob:
    for _ in range(max_polls):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state in time")


@pytest.mark.asyncio
async def test_write_scene_happy_path(client, db_engine, db_session, monkeypatch):
    """write_scene 闭环：draft 落库、状态推进、quota 消耗和 model_calls 指标。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, _, scene_id, headers = await _setup_org_project_spec_scene(
        client, db_session, email="write-happy@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/write",
        headers=headers,
        json={"target_words": 1200},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.consumed_quota == 1200
    assert job.output_payload["memory"]["updated_character_count"] == 1

    db_session.expire_all()
    drafts = (
        await db_session.execute(
            select(DraftVersion).where(DraftVersion.scene_id == scene_id)
        )
    ).scalars().all()
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.version_type == "draft"
    assert draft.content
    assert draft.parent_version_id is None  # 第一次生成无父版本

    scene = await db_session.get(Scene, scene_id)
    assert scene.status == "drafted"
    character = (
        await db_session.execute(
            select(Character).where(
                Character.project_id == project_id,
                Character.name == "林澈",
            )
        )
    ).scalar_one()
    assert character.current_state["last_scene_title"] == "开场场景"
    assert character.current_state["knowledge_state"] == "档案被人篡改"

    character_memories = (
        await db_session.execute(
            select(MemoryEntry).where(
                MemoryEntry.project_id == project_id,
                MemoryEntry.source_id == scene_id,
                MemoryEntry.memory_type == "character_state",
            )
        )
    ).scalars().all()
    assert len(character_memories) == 1
    assert "林澈" in character_memories[0].title
    memory_res = await client.get(
        f"/api/v1/projects/{project_id}/memory",
        headers=headers,
        params={"memory_type": "character_state", "character": "林澈"},
    )
    assert memory_res.status_code == 200
    assert len(memory_res.json()) == 1

    # model_calls 应该记录 ContextBuilder 诊断指标
    model_calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    assert {call.task_type for call in model_calls} >= {
        "write_scene_draft",
        "update_character_states",
    }

    usage = (
        await db_session.execute(select(UsageEvent).where(UsageEvent.job_id == job_id))
    ).scalar_one()
    assert usage.amount == 1200

    reservation = (
        await db_session.execute(
            select(QuotaReservation).where(QuotaReservation.job_id == job_id)
        )
    ).scalar_one()
    assert reservation.status == "consumed"


@pytest.mark.asyncio
async def test_write_scene_chains_parent_version_on_regenerate(
    client, db_engine, db_session, monkeypatch
):
    """第二次生成时 parent_version_id 指向第一次的版本，构成 draft 链。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, _, scene_id, headers = await _setup_org_project_spec_scene(
        client, db_session, email="write-chain@example.com"
    )

    # 第一次写
    res1 = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/write",
        headers=headers,
        json={"target_words": 1000},
    )
    job1_id = res1.json()["id"]
    await _await_job_terminal(db_session, job1_id)

    db_session.expire_all()
    first_drafts = (
        await db_session.execute(
            select(DraftVersion).where(DraftVersion.scene_id == scene_id)
        )
    ).scalars().all()
    assert len(first_drafts) == 1
    first_version_id = first_drafts[0].id

    # 第二次写：应该产出新 draft，parent 指向第一次
    res2 = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/write",
        headers=headers,
        json={"target_words": 1000},
    )
    job2_id = res2.json()["id"]
    await _await_job_terminal(db_session, job2_id)

    db_session.expire_all()
    all_drafts = (
        await db_session.execute(
            select(DraftVersion).where(DraftVersion.scene_id == scene_id)
        )
    ).scalars().all()
    assert len(all_drafts) == 2

    # 找出新版本（id 不是第一次的那个）
    new_draft = next(d for d in all_drafts if d.id != first_version_id)
    assert new_draft.parent_version_id == first_version_id


@pytest.mark.asyncio
async def test_write_scene_rejects_missing_scene(client, db_engine, db_session, monkeypatch):
    """scene_id 不存在 → 404 scene_not_found（在 activity 内捕获）。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, _, _, headers = await _setup_org_project_spec_scene(
        client,
        db_session,
        email="write-missing-scene@example.com",
        with_scene=False,
    )

    bogus_scene = "scene_does_not_exist"
    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{bogus_scene}/write",
        headers=headers,
        json={"target_words": 1000},
    )
    # API 层不校验 scene 存在（避免与 activity 重复逻辑），返回 202；
    # 然后 activity 内部抛 scene_not_found → job 走 failed 路径。
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]
    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "failed"
    assert "scene_not_found" in (job.error_message or "")


@pytest.mark.asyncio
async def test_write_scene_releases_quota_on_failure(client, db_engine, db_session, monkeypatch):
    """模型抛异常 → job=failed + quota 释放。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, _, scene_id, headers = await _setup_org_project_spec_scene(
        client, db_session, email="write-fail@example.com"
    )

    from app.services.writer.service import writer_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_writer_failure")

    monkeypatch.setattr(writer_service, "write_scene_draft", _boom)

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/write",
        headers=headers,
        json={"target_words": 1500},
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


@pytest.mark.asyncio
async def test_write_scene_rejects_cross_tenant(client, db_engine, db_session, monkeypatch):
    """org B 不能为 org A 的 scene 触发写作 → 404。

    org B 也升级到 Pro plan 让 entitlement 通过，确保测试真的能走到租户
    隔离检查（否则会被 402 entitlement_required 提前拦截，掩盖真实问题）。
    """
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, _, scene_a, _ = await _setup_org_project_spec_scene(
        client, db_session, email="write-org-a@example.com"
    )
    token_b, org_b = await _register(client, "write-org-b@example.com")
    org_b_row = await db_session.get(Organization, org_b)
    org_b_row.plan_code = "Pro"
    await db_session.commit()
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.post(
        f"/api/v1/projects/{project_a}/scenes/{scene_a}/write",
        headers=headers_b,
        json={"target_words": 1000},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "project_not_found"
