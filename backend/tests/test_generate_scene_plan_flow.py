from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    GenerationJob,
    MemoryEntry,
    ModelCall,
    NovelSpec,
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


async def _setup_org_project_spec_and_chapter(
    client,
    db_session,
    *,
    email: str,
    limit_value: int = 10000,
) -> tuple[str, str, str, dict]:
    """注册 + quota + project + NovelSpec + 1 chapter。

    返回 (org_id, project_id, chapter_id, headers)。
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
    chapter_id = new_id("chapter")
    db_session.add(
        NovelSpec(
            id=new_id("spec"),
            organization_id=org_id,
            project_id=project_id,
            premise="测试前提",
            theme="测试主题",
            genre="测试",
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
    # 把项目推到 outlined 模拟 outline 已完成
    project = await db_session.get(Project, project_id)
    project.status = "outlined"
    await db_session.commit()
    return org_id, project_id, chapter_id, headers


async def _await_job_terminal(db_session, job_id: str, *, max_polls: int = 30) -> GenerationJob:
    for _ in range(max_polls):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state in time")


@pytest.mark.asyncio
async def test_generate_scene_plan_happy_path(client, db_engine, db_session, monkeypatch):
    """生成单章 scenes → scenes 落库 + memory_entries 写入 + quota 消耗。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, chapter_id, headers = await _setup_org_project_spec_and_chapter(
        client, db_session, email="scene-happy@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/scenes/generate",
        headers=headers,
        json={
            "scenes_per_chapter": 3,
            "expected_words": 1200,
            "estimate_words": 2000,
        },
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["job_type"] == "generate_scene_plan"
    job_id = body["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.consumed_quota == 2000
    assert (job.output_payload or {}).get("chapter_id") == chapter_id
    assert (job.output_payload or {}).get("scene_count") == 3
    assert (job.output_payload or {}).get("reused") is False

    db_session.expire_all()
    scenes = (
        await db_session.execute(
            select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.scene_index)
        )
    ).scalars().all()
    assert len(scenes) == 3
    for s in scenes:
        assert s.title
        assert s.scene_purpose
        assert s.entry_state
        assert s.exit_state
        assert s.goal
        assert s.conflict
        assert s.must_include
        assert s.must_avoid

    # memory_entries：每个 scene 一条 source_type=scene 的摘要
    memories = (
        await db_session.execute(
            select(MemoryEntry).where(
                MemoryEntry.project_id == project_id,
                MemoryEntry.source_type == "scene",
            )
        )
    ).scalars().all()
    assert len(memories) == 3
    assert {m.source_id for m in memories} == {s.id for s in scenes}

    model_calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    assert len(model_calls) >= 1
    assert all(mc.prompt_key == "outline/plan_scenes" for mc in model_calls)

    usage = (
        await db_session.execute(select(UsageEvent).where(UsageEvent.job_id == job_id))
    ).scalar_one()
    assert usage.amount == 2000

    reservation = (
        await db_session.execute(
            select(QuotaReservation).where(QuotaReservation.job_id == job_id)
        )
    ).scalar_one()
    assert reservation.status == "consumed"

    # 单章生成不动 project.status
    project = await db_session.get(Project, project_id)
    assert project.status == "outlined"


@pytest.mark.asyncio
async def test_generate_scene_plan_auto_scene_count(client, db_engine, db_session, monkeypatch):
    """不传 scenes_per_chapter 时，由模型在 1-8 范围内自行拆分。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, chapter_id, headers = await _setup_org_project_spec_and_chapter(
        client,
        db_session,
        email="scene-auto@example.com",
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/scenes/generate",
        headers=headers,
        json={"expected_words": 1200, "estimate_words": 2000},
    )
    assert res.status_code == 202, res.text
    job = await _await_job_terminal(db_session, res.json()["id"])
    assert job.status == "succeeded"
    assert job.input_payload["scenes_per_chapter"] is None
    assert (job.output_payload or {}).get("scene_count") == 4

    db_session.expire_all()
    scenes = (
        await db_session.execute(
            select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.scene_index)
        )
    ).scalars().all()
    assert len(scenes) == 4
    assert all(scene.entry_state and scene.exit_state for scene in scenes)


@pytest.mark.asyncio
async def test_generate_scene_plan_rejects_without_bible(
    client, db_engine, db_session, monkeypatch
):
    """缺 NovelSpec → 404 novel_spec_not_found。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    token, org_id = await _register(client, "scene-nobible@example.com")
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
        json={"title": "无 bible 项目"},
    )
    project_id = project_res.json()["id"]
    chapter_id = new_id("chapter")
    db_session.add(
        Chapter(
            id=chapter_id,
            organization_id=org_id,
            project_id=project_id,
            volume_id=None,
            chapter_index=1,
            title="孤章",
            summary="—",
            goal="—",
            conflict="—",
            ending_hook="—",
            status="planned",
        )
    )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 3},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "novel_spec_not_found"


@pytest.mark.asyncio
async def test_generate_scene_plan_rejects_missing_chapter(
    client, db_engine, db_session, monkeypatch
):
    """chapter_id 不存在或不属于该 project → 404 chapter_not_found。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, _, headers = await _setup_org_project_spec_and_chapter(
        client, db_session, email="scene-missing-chapter@example.com"
    )

    bogus_chapter = "chapter_does_not_exist"
    res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{bogus_chapter}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 3},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "chapter_not_found"


@pytest.mark.asyncio
async def test_generate_scene_plan_releases_quota_on_failure(
    client, db_engine, db_session, monkeypatch
):
    """plan_scenes 抛异常 → job=failed + quota 释放（project.status 不动）。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, chapter_id, headers = await _setup_org_project_spec_and_chapter(
        client, db_session, email="scene-fail@example.com"
    )

    from app.services.novel_planner.service import novel_planner_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_planner_failure")

    monkeypatch.setattr(novel_planner_service, "plan_scenes", _boom)

    res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 3, "estimate_words": 2000},
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

    # 单章 scene_plan 失败时不回滚 project.status（不在 _JOB_FAILURE_PROJECT_STATUS 中）
    project = await db_session.get(Project, project_id)
    assert project.status == "outlined"


@pytest.mark.asyncio
async def test_generate_scene_plan_reuses_existing_scenes(
    client, db_engine, db_session, monkeypatch
):
    """该章已有 scenes 且 force_regenerate=False 时走 reuse 分支，不扣额度。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, chapter_id, headers = await _setup_org_project_spec_and_chapter(
        client, db_session, email="scene-reuse@example.com"
    )

    # 预置 2 个 scenes
    for idx in range(1, 3):
        db_session.add(
            Scene(
                id=new_id("scene"),
                organization_id=org_id,
                project_id=project_id,
                chapter_id=chapter_id,
                scene_index=idx,
                title=f"已存在场景 {idx}",
                time_marker="—",
                location="—",
                characters=[],
                goal="—",
                conflict="—",
                emotion_start="—",
                emotion_end="—",
                reveal="—",
                hook="—",
                status="planned",
            )
        )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/scenes/generate",
        headers=headers,
        json={"scenes_per_chapter": 4, "force_regenerate": False},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.consumed_quota == 0
    assert (job.output_payload or {}).get("reused") is True
    assert (job.output_payload or {}).get("scene_count") == 2

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


@pytest.mark.asyncio
async def test_generate_scene_plan_rejects_cross_tenant(
    client, db_engine, db_session, monkeypatch
):
    """org B 不能为 org A 的 chapter 生成 scenes → 404。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, chapter_a, _ = await _setup_org_project_spec_and_chapter(
        client, db_session, email="scene-org-a@example.com"
    )
    token_b, _ = await _register(client, "scene-org-b@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.post(
        f"/api/v1/projects/{project_a}/chapters/{chapter_a}/scenes/generate",
        headers=headers_b,
        json={"scenes_per_chapter": 3},
    )
    assert res.status_code == 404, res.text
    # tenant 隔离在 project 层先拦截
    assert res.json()["error"]["message"] == "project_not_found"


# ---------------------------------------------------------------------------
# ContextBuilder 单元测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_builder_assemble_basic_segments(db_session):
    """ContextBuilder.build_for_scene_planning 返回 7 段，trusted 标记正确。"""
    from app.services.context_builder import ContextBuilder

    builder = ContextBuilder(total_budget=4000)

    org_id = new_id("org")
    project_id = new_id("project")
    project = Project(
        id=project_id,
        organization_id=org_id,
        created_by="user_x",
        title="测试项目",
        genre="奇幻",
        target_word_count=50000,
        target_chapter_count=6,
        language="zh-CN",
        style="冷峻",
        status="outlined",
        cover_url="",
        tags=[],
        target_reader="—",
    )
    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="测试前提",
        theme="测试主题",
        genre="奇幻",
        tone="紧张",
        target_reader="—",
        narrative_pov="第三人称",
        style_guide="画面优先",
        constraints=["保持视角一致"],
        continuity_rules=["主角不能轻易死亡"],
    )
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="开端",
        summary="开端摘要",
        goal="建立背景",
        conflict="初始矛盾",
        ending_hook="抛出问题",
        status="planned",
    )
    db_session.add_all([project, spec, chapter])
    await db_session.commit()

    ctx = await builder.build_for_scene_planning(
        db_session, project=project, spec=spec, chapter=chapter
    )

    # 必须是 7 段顺序
    labels = [s.label for s in ctx.segments]
    assert labels == [
        "hard_constraints",
        "task",
        "characters",
        "world_rules",
        "plot_threads",
        "recent_summary",
        "memory_recall",
    ]
    # trusted 标记
    trusted_labels = {s.label for s in ctx.segments if s.trusted}
    assert "hard_constraints" in trusted_labels
    assert "task" in trusted_labels
    untrusted_labels = {s.label for s in ctx.segments if not s.trusted}
    assert untrusted_labels == {"memory_recall"}

    # hard_constraints 应该有内容（spec 非空）
    hc = next(s for s in ctx.segments if s.label == "hard_constraints")
    assert "测试前提" in hc.content
    assert "测试主题" in hc.content
    assert "保持视角一致" in hc.content

    # to_prompt 应该跳过空段（characters/world_rules/plot_threads/memory_recall）
    prompt = ctx.to_prompt()
    assert "[hard_constraints]" in prompt
    assert "[task]" in prompt
    assert "[characters]" not in prompt  # 没有 character 数据
    assert "[memory_recall]" not in prompt  # 没有 memory 数据
