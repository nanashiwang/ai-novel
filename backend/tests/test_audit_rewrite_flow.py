from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    ContinuityIssue,
    DraftVersion,
    GenerationJob,
    ModelCall,
    NovelSpec,
    Organization,
    Project,
    QuotaBalance,
    QuotaReservation,
    Scene,
    StoryStateItem,
)
from app.models.common import new_id
from app.schemas.story_generation import AuditIssueItem, AuditResultContract
from app.workflows import activities


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


async def _setup_with_draft(
    client,
    db_session,
    *,
    email: str,
    plan: str = "Pro",
    with_draft: bool = True,
) -> tuple[str, str, str, str, str | None, dict]:
    """注册 + quota + project + spec + chapter + scene + 可选 draft。

    返回 (org_id, project_id, chapter_id, scene_id, draft_id?, headers)。
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
            limit_value=10000,
            used_value=0,
            reserved_value=0,
            reset_at=now + timedelta(days=30),
        )
    )
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "审稿测试", "target_chapter_count": 3, "target_word_count": 30000},
    )
    project_id = project_res.json()["id"]
    chapter_id = new_id("chapter")
    scene_id = new_id("scene")
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
            summary="开局",
            goal="建立背景",
            conflict="初始冲突",
            ending_hook="留悬念",
            status="planned",
        )
    )
    db_session.add(
        Scene(
            id=scene_id,
            organization_id=org_id,
            project_id=project_id,
            chapter_id=chapter_id,
            scene_index=1,
            title="开场",
            time_marker="清晨",
            location="档案馆",
            characters=["林澈"],
            goal="进入档案室",
            conflict="门禁失效",
            emotion_start="平静",
            emotion_end="警觉",
            reveal="发现被篡改痕迹",
            hook="找到陌生符号",
            status="drafted",
        )
    )
    draft_id: str | None = None
    if with_draft:
        draft_id = new_id("draft")
        db_session.add(
            DraftVersion(
                id=draft_id,
                organization_id=org_id,
                project_id=project_id,
                chapter_id=chapter_id,
                scene_id=scene_id,
                version_type="draft",
                content="某个清晨的开场草稿（用于审稿测试）。",
                word_count=18,
                status="draft",
                parent_version_id=None,
                created_by="user_x",
            )
        )
    project = await db_session.get(Project, project_id)
    project.status = "drafting"
    org_row = await db_session.get(Organization, org_id)
    org_row.plan_code = plan
    await db_session.commit()
    return org_id, project_id, chapter_id, scene_id, draft_id, headers


async def _await_job_terminal(db_session, job_id: str, *, max_polls: int = 30) -> GenerationJob:
    for _ in range(max_polls):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state in time")


@pytest.mark.asyncio
async def test_audit_scene_writes_issues(client, db_engine, db_session, monkeypatch):
    """审稿 happy path：调用后 continuity_issues 至少写入一条，quota 消耗。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, _, scene_id, _, headers = await _setup_with_draft(
        client, db_session, email="audit-happy@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/audit",
        headers=headers,
        json={"estimate_words": 500},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.job_type == "audit_scene"
    assert job.consumed_quota == 500

    db_session.expire_all()
    issues = (
        await db_session.execute(
            select(ContinuityIssue).where(ContinuityIssue.scene_id == scene_id)
        )
    ).scalars().all()
    assert len(issues) >= 1
    for issue in issues:
        assert issue.severity in {"low", "medium", "high"}
        assert issue.issue_type in {"continuity", "character", "world_rule", "style"}
        assert issue.status == "open"
        assert issue.description

    list_res = await client.get(
        f"/api/v1/projects/{project_id}/continuity-issues",
        headers=headers,
    )
    assert list_res.status_code == 200
    api_issues = [issue for issue in list_res.json() if issue["scene_id"] == scene_id]
    assert len(api_issues) == len(issues)
    assert api_issues[0]["chapter_id"] is not None


@pytest.mark.asyncio
async def test_audit_scene_persists_story_state_link(
    client, db_engine, db_session, monkeypatch
):
    """审稿返回 story_state_item_id 时，落库并透出到 continuity issues API。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, chapter_id, scene_id, _, headers = await _setup_with_draft(
        client, db_session, email="audit-state-link@example.com"
    )
    state_id = new_id("state")
    db_session.add(
        StoryStateItem(
            id=state_id,
            organization_id=org_id,
            project_id=project_id,
            entity_type="artifact",
            entity_id=None,
            state_type="artifact",
            name="因果印",
            status="damaged",
            summary="因果印已有裂痕，不能写成完好无损。",
            value_json={},
            source_chapter_id=chapter_id,
            source_scene_id=scene_id,
            source_excerpt="因果印出现裂痕。",
            updated_in_chapter_id=chapter_id,
            priority=90,
            is_hard_constraint=True,
        )
    )
    await db_session.commit()

    async def _review_with_state_link(*args, **kwargs):
        return AuditResultContract(
            issues=[
                AuditIssueItem(
                    issue_type="设定冲突",
                    severity="高",
                    description="正文把因果印写成完好无损，与关键状态冲突。",
                    suggested_fix="把因果印改为裂痕反噬状态。",
                    story_state_item_id=state_id,
                )
            ]
        )

    monkeypatch.setattr(activities.auditor_service, "audit_scene_draft", _review_with_state_link)

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/audit",
        headers=headers,
        json={"estimate_words": 500},
    )
    assert res.status_code == 202, res.text
    job = await _await_job_terminal(db_session, res.json()["id"])
    assert job.status == "succeeded"

    db_session.expire_all()
    issue = (
        await db_session.execute(
            select(ContinuityIssue).where(ContinuityIssue.scene_id == scene_id)
        )
    ).scalar_one()
    assert issue.issue_type == "state_conflict"
    assert issue.severity == "high"
    assert issue.story_state_item_id == state_id

    list_res = await client.get(
        f"/api/v1/projects/{project_id}/continuity-issues",
        headers=headers,
    )
    assert list_res.status_code == 200
    api_issue = next(issue for issue in list_res.json() if issue["scene_id"] == scene_id)
    assert api_issue["story_state_item_id"] == state_id


@pytest.mark.asyncio
async def test_audit_scene_triggers_story_state_maintenance_after_issues(
    client, db_engine, db_session, monkeypatch
):
    """审稿写入问题后，应继续触发 AI 关键设定维护器。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, chapter_id, scene_id, draft_id, headers = await _setup_with_draft(
        client, db_session, email="audit-maintenance@example.com"
    )
    assert draft_id is not None
    state_id = new_id("state")
    db_session.add(
        StoryStateItem(
            id=state_id,
            organization_id=org_id,
            project_id=project_id,
            entity_type="artifact",
            entity_id=None,
            state_type="artifact",
            name="因果印",
            status="damaged",
            summary="因果印已有裂痕。",
            value_json={},
            source_chapter_id=chapter_id,
            source_scene_id=scene_id,
            source_excerpt="因果印出现裂痕。",
            updated_in_chapter_id=chapter_id,
            priority=90,
            is_hard_constraint=True,
        )
    )
    await db_session.commit()

    async def _review_with_state_issue(*args, **kwargs):
        return AuditResultContract(
            issues=[
                AuditIssueItem(
                    issue_type="state_conflict",
                    severity="medium",
                    description="正文遗漏因果印裂痕承接。",
                    suggested_fix="补充因果印裂痕仍在。",
                    story_state_item_id=state_id,
                )
            ]
        )

    captured: dict[str, str] = {}

    async def _fake_maintenance(*args, **kwargs):
        captured["source"] = kwargs["source"]
        captured["draft_id"] = kwargs["draft"].id
        captured["scene_id"] = kwargs["scene"].id
        return {
            "suggested_count": 0,
            "applied_count": 1,
            "needs_review_count": 0,
            "skipped_count": 0,
            "action_count": 1,
            "action_ids": ["state_action_test"],
        }

    monkeypatch.setattr(activities.auditor_service, "audit_scene_draft", _review_with_state_issue)
    monkeypatch.setattr(activities, "_run_story_state_maintenance", _fake_maintenance)

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/audit",
        headers=headers,
        json={"estimate_words": 500},
    )
    assert res.status_code == 202, res.text
    job = await _await_job_terminal(db_session, res.json()["id"])
    assert job.status == "succeeded"
    assert captured == {
        "source": "audit_scene",
        "draft_id": draft_id,
        "scene_id": scene_id,
    }
    assert job.output_payload["story_state_maintenance"]["applied_count"] == 1
    assert job.output_payload["story_state_maintenance"]["action_ids"] == [
        "state_action_test"
    ]


@pytest.mark.asyncio
async def test_audit_scene_rejects_without_draft(client, db_engine, db_session, monkeypatch):
    """没有 draft 时审稿任务在 activity 内失败（draft_not_found）。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, _, scene_id, _, headers = await _setup_with_draft(
        client, db_session, email="audit-nodraft@example.com", with_draft=False
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/audit",
        headers=headers,
        json={"estimate_words": 500},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "failed"
    assert "draft_not_found" in (job.error_message or "")


@pytest.mark.asyncio
async def test_rewrite_scene_fixes_issues_and_chains_version(
    client, db_engine, db_session, monkeypatch
):
    """重写后：

    - DraftVersion(version_type='rewrite') 写入，parent 指向原 draft
    - 自动复审无问题时，原 open issues 全部 status='fixed'
    - quota 消耗
    """
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    async def _clean_review(*args, **kwargs):
        return AuditResultContract(issues=[])

    monkeypatch.setattr(activities.auditor_service, "audit_scene_draft", _clean_review)

    org_id, project_id, chapter_id, scene_id, draft_id, headers = await _setup_with_draft(
        client, db_session, email="rewrite-happy@example.com"
    )
    assert draft_id is not None

    # 预置两条 open issues
    for i in range(2):
        db_session.add(
            ContinuityIssue(
                id=new_id("issue"),
                organization_id=org_id,
                project_id=project_id,
                chapter_id=chapter_id,
                scene_id=scene_id,
                issue_type="continuity",
                severity="medium",
                description=f"测试问题 {i + 1}",
                suggested_fix="测试修复建议",
                status="open",
            )
        )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/rewrite",
        headers=headers,
        json={"target_words": 1000, "estimate_words": 2000},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    job = await _await_job_terminal(db_session, job_id)
    assert job.status == "succeeded"
    assert job.consumed_quota == 2000
    assert job.output_payload["review_passed"] is True
    assert job.output_payload["fixed_issue_count"] == 2

    db_session.expire_all()
    drafts = (
        await db_session.execute(
            select(DraftVersion).where(DraftVersion.scene_id == scene_id)
        )
    ).scalars().all()
    rewrite_drafts = [d for d in drafts if d.version_type == "rewrite"]
    assert len(rewrite_drafts) == 1
    assert rewrite_drafts[0].parent_version_id == draft_id

    issues = (
        await db_session.execute(
            select(ContinuityIssue).where(ContinuityIssue.scene_id == scene_id)
        )
    ).scalars().all()
    assert {i.status for i in issues} == {"fixed"}

    scene = await db_session.get(Scene, scene_id)
    assert scene.status == "drafted"

    model_calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    assert {call.task_type for call in model_calls} >= {
        "rewrite_scene",
        "postprocess_rewrite_draft",
    }


@pytest.mark.asyncio
async def test_rewrite_scene_keeps_issue_open_when_auto_review_still_finds_it(
    client, db_engine, db_session, monkeypatch
):
    """重写后自动复审仍发现同一问题时，不把原 issue 标 fixed。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    async def _review_same_issue(*args, **kwargs):
        return AuditResultContract(
            issues=[
                AuditIssueItem(
                    issue_type="continuity",
                    severity="medium",
                    description="测试问题仍未解决：关键道具属性仍不一致",
                    suggested_fix="测试修复建议",
                )
            ]
        )

    monkeypatch.setattr(activities.auditor_service, "audit_scene_draft", _review_same_issue)

    org_id, project_id, chapter_id, scene_id, _, headers = await _setup_with_draft(
        client, db_session, email="rewrite-review-open@example.com"
    )
    issue_id = new_id("issue")
    db_session.add(
        ContinuityIssue(
            id=issue_id,
            organization_id=org_id,
            project_id=project_id,
            chapter_id=chapter_id,
            scene_id=scene_id,
            issue_type="continuity",
            severity="medium",
            description="测试问题：关键道具属性仍不一致",
            suggested_fix="测试修复建议",
            status="open",
        )
    )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/rewrite",
        headers=headers,
        json={"target_words": 1000, "estimate_words": 2000},
    )
    assert res.status_code == 202, res.text
    job = await _await_job_terminal(db_session, res.json()["id"])
    assert job.status == "succeeded"
    assert job.output_payload["review_passed"] is False
    assert job.output_payload["fixed_issue_count"] == 0
    assert job.output_payload["remaining_issue_count"] == 1

    db_session.expire_all()
    issues = (
        await db_session.execute(
            select(ContinuityIssue).where(ContinuityIssue.scene_id == scene_id)
        )
    ).scalars().all()
    assert len(issues) == 1
    assert issues[0].id == issue_id
    assert issues[0].status == "open"


@pytest.mark.asyncio
async def test_rewrite_scene_releases_quota_on_failure(client, db_engine, db_session, monkeypatch):
    """rewriter 失败 → quota 释放。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    org_id, project_id, _, scene_id, _, headers = await _setup_with_draft(
        client, db_session, email="rewrite-fail@example.com"
    )

    from app.services.rewriter.service import rewriter_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated_rewriter_failure")

    monkeypatch.setattr(rewriter_service, "rewrite_scene_draft", _boom)

    res = await client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/rewrite",
        headers=headers,
        json={"target_words": 1000, "estimate_words": 2000},
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
async def test_rewrite_scene_rejects_cross_tenant(client, db_engine, db_session, monkeypatch):
    """org B 不能为 org A 的 scene 触发重写 → 404。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, _, scene_a, _, _ = await _setup_with_draft(
        client, db_session, email="rewrite-org-a@example.com"
    )
    token_b, org_b = await _register(client, "rewrite-org-b@example.com")
    org_b_row = await db_session.get(Organization, org_b)
    org_b_row.plan_code = "Pro"
    await db_session.commit()
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.post(
        f"/api/v1/projects/{project_a}/scenes/{scene_a}/rewrite",
        headers=headers_b,
        json={"target_words": 1000},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "project_not_found"
