from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Chapter,
    Character,
    ContinuityIssue,
    DraftVersion,
    GenerationJob,
    MemoryEntry,
    ModelCall,
    NovelSpec,
    Organization,
    PlotThread,
    Project,
    QuotaBalance,
    RevisionAppliedChange,
    RevisionProposal,
    RevisionSession,
    Scene,
    WorldItem,
)
from app.models.common import new_id


async def _register_with_project(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "作者"},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    project = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "雾城记忆案",
            "premise": "档案员发现城市记忆被买卖。",
            "genre": "悬疑幻想",
            "style": "冷峻克制",
            "target_reader": "类型小说读者",
        },
    )
    assert project.status_code == 201, project.text
    return token, project.json()["id"]


async def _seed_project_quota(db_session, project_id: str, limit: int = 50_000) -> None:
    project = await db_session.get(Project, project_id)
    assert project is not None
    now = datetime.now(timezone.utc)
    db_session.add(
        QuotaBalance(
            id=new_id("quota"),
            organization_id=project.organization_id,
            quota_key="monthly_generated_words",
            period_start=now,
            period_end=now + timedelta(days=30),
            limit_value=limit,
            used_value=0,
            reserved_value=0,
            reset_at=now + timedelta(days=30),
        )
    )
    await db_session.commit()


def _bundle_story_bible() -> dict:
    return {
        "premise": "许亦舟在南城高中发现现实被折页界改写，必须靠升级能力夺回人生主线。",
        "theme": "少年在异能规则、阶层压力和现实叙事权争夺中完成自我掌控。",
        "genre": "男频校园异能升级流",
        "tone": "热血、悬疑、快节奏",
        "target_reader": "男频类型小说读者",
        "narrative_pov": "第三人称有限视角，主要跟随许亦舟",
        "style_guide": "校园日常与折页界冒险交替推进，每章必须有升级点和钩子。",
        "constraints": ["不直接优化正文"],
        "locations": [
            {
                "name": "南城一中",
                "description": "现实世界的主舞台，也是折页界裂缝最密集的学校。",
                "importance": "high",
            }
        ],
        "factions": [
            {
                "name": "校勘委员会",
                "description": "负责维持现实文本稳定的隐秘组织。",
                "importance": "high",
            }
        ],
        "world_rules": ["折页界每次改写都会收取现实代价。"],
        "main_characters": [
            {
                "name": "许亦舟",
                "role": "protagonist",
                "description": "被卷入折页界的普通高中生。",
                "personality": "冷静但不服输",
                "motivation": "找回被改写的人生主线。",
                "secret": "童年曾被折页界标记。",
                "arc": "从被动求生到主动改写规则。",
                "relationships": {"林照夏": "关键盟友"},
                "current_state": {"status": "刚发现折页界"},
            }
        ],
        "continuity_rules": ["secret 只能在关键转折后逐步揭示。"],
        "plot_threads": ["许亦舟追查折页界源头并挑战校勘委员会。"],
    }


def _bundle_patch() -> dict:
    return {"story_bible": _bundle_story_bible(), "rewrite_plan": "重构为男频校园升级流"}


class BundleProvider:
    async def complete_json(self, **_: object) -> dict:
        return {
            "reply": "已生成完整新版故事圣经。",
            "summary": "从校园群像重构为男频校园异能升级主线。",
            "risk_notes": ["旧正文需要重建。"],
            "story_bible": _bundle_story_bible(),
        }

    async def complete_text(self, **_: object) -> str:
        return ""


@pytest.mark.asyncio
async def test_revision_chat_creates_applyable_proposals(client, db_session):
    token, project_id = await _register_with_project(client, "revision@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    chat = await client.post(
        f"/api/v1/projects/{project_id}/revisions/chat",
        headers=headers,
        json={"message": "请帮我强化主题，并补足灰市相关设定。"},
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["session"]["project_id"] == project_id
    assert body["reply"]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert len(body["proposals"]) == 4
    assert all("group_id" in p and "risk_notes" in p for p in body["proposals"])
    assert {p["target_type"] for p in body["proposals"]} == {
        "story_bible",
        "character",
        "world_item",
        "plot_thread",
    }

    for proposal in body["proposals"]:
        applied = await client.post(
            f"/api/v1/projects/{project_id}/revisions/proposals/{proposal['id']}/apply",
            headers=headers,
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["proposal"]["status"] == "applied"

    spec = await client.get(f"/api/v1/projects/{project_id}/spec", headers=headers)
    assert spec.status_code == 200
    assert spec.json()["theme"] == "记忆交易背后的代价与自我选择"

    characters = await client.get(f"/api/v1/projects/{project_id}/characters", headers=headers)
    assert any(row["name"] == "顾眠" for row in characters.json())

    world_items = await client.get(f"/api/v1/projects/{project_id}/world-items", headers=headers)
    assert any(row["name"] == "记忆等价交换" for row in world_items.json())

    threads = await client.get(f"/api/v1/projects/{project_id}/plot-threads", headers=headers)
    assert any(row["title"] == "灰市记忆样本追查" for row in threads.json())

    changes = (await db_session.execute(select(RevisionAppliedChange))).scalars().all()
    assert len(changes) == 4
    assert any(change.before_data == {} for change in changes)
    assert any(
        change.after_data.get("theme") == "记忆交易背后的代价与自我选择" for change in changes
    )

    duplicated = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{body['proposals'][0]['id']}/apply",
        headers=headers,
    )
    assert duplicated.status_code == 409
    assert duplicated.json()["error"]["code"] == "revision_proposal_already_applied"


@pytest.mark.asyncio
async def test_revision_chat_converts_advice_shape_to_applyable_proposals(
    client,
    db_session,
):
    from app.services.model_gateway.service import model_gateway

    class AdviceShapeProvider:
        async def complete_json(self, **_: object) -> dict:
            return {
                "reply": "已整理 3 个优化方向。",
                "proposals": [
                    {
                        "title": "确立男频主轴",
                        "problem": "当前主角体系混杂。",
                        "core_adjustment": "以许亦舟为唯一男主，重构成长主线。",
                        "long_form_value": "形成稳定升级、破局和势力博弈。",
                        "application_notes": ["女性角色转为关键盟友。"],
                        "male_lead_profile": {
                            "name": "许亦舟",
                            "role": "男主角",
                            "surface_identity": "普通高一男生。",
                            "core_motivation": "洗清误会并追查折页界真相。",
                            "secret": "童年曾进入页缝。",
                            "ability_arc": "从发现异常到重写毕业规则。",
                        },
                    },
                    {
                        "title": "扩展折页界",
                        "problem": "世界观范围偏小。",
                        "core_adjustment": "折页界升级为城市级记忆暗面。",
                        "rule_upgrades": [
                            {"rule": "所有改写都有现实后果。"},
                        ],
                    },
                    {
                        "title": "建立多方势力格局",
                        "problem": "缺少阵营博弈。",
                        "core_adjustment": "围绕现实叙事权建立六大势力。",
                        "factions": [
                            {
                                "name": "校勘委员会",
                                "goal": "维持现实稳定。",
                                "leader": "陈问渠",
                                "method": "牺牲少数高风险个体。",
                            }
                        ],
                    },
                ],
            }

        async def complete_text(self, **_: object) -> str:
            return ""

    token, project_id = await _register_with_project(client, "revision-advice@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None
    db_session.add(
        Character(
            id="char_xuyizhou",
            organization_id=project.organization_id,
            project_id=project_id,
            name="许亦舟",
            role="学生",
            description="旧设定",
        )
    )
    await db_session.commit()
    model_gateway.set_provider(AdviceShapeProvider())

    chat = await client.post(
        f"/api/v1/projects/{project_id}/revisions/chat",
        headers=headers,
        json={"message": "请改成男频主轴，并扩展世界观。"},
    )

    assert chat.status_code == 200, chat.text
    proposals = chat.json()["proposals"]
    assert proposals
    assert {p["target_type"] for p in proposals} >= {
        "story_bible",
        "character",
        "world_item",
        "plot_thread",
    }
    assert all(p["patch"] for p in proposals)


@pytest.mark.asyncio
async def test_revision_chat_converts_real_advice_only_shape(client):
    from app.services.model_gateway.service import model_gateway

    class RealAdviceProvider:
        async def complete_json(self, **_: object) -> dict:
            return {
                "reply": "给出 3 个方向。",
                "proposals": [
                    {
                        "type": "positioning",
                        "title": "类型定位调整为男频校园异能悬疑升级流",
                        "content": "核心卖点从青春群像转为许亦舟升级破局。",
                        "implementation": ["Premise 改为折页界升级主线", "每章保留升级钩子"],
                    },
                    {
                        "type": "protagonist",
                        "title": "统一男主成长主轴",
                        "content": "许亦舟承担唯一行动主线，其他角色围绕其成长形成助力与阻力。",
                        "implementation": ["强化动机", "补足秘密", "设计能力弧光"],
                    },
                    {
                        "type": "worldbuilding",
                        "title": "显著提高折页界戏份",
                        "content": "折页界从点缀变成核心世界规则。",
                        "implementation": ["建立现实改写代价", "扩展校勘委员会"],
                    },
                ],
            }

        async def complete_text(self, **_: object) -> str:
            return ""

    token, project_id = await _register_with_project(
        client,
        "revision-real-advice@example.com",
    )
    model_gateway.set_provider(RealAdviceProvider())

    chat = await client.post(
        f"/api/v1/projects/{project_id}/revisions/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "改成男频折页界升级流。"},
    )

    assert chat.status_code == 200, chat.text
    proposals = chat.json()["proposals"]
    assert proposals
    assert all(p["patch"] for p in proposals)
    assert {p["target_type"] for p in proposals} >= {"story_bible", "plot_thread"}


@pytest.mark.asyncio
async def test_full_project_rewrite_creates_story_bible_bundle(client, db_session):
    from app.services.model_gateway.service import model_gateway
    from app.workflows.starter import workflow_starter

    model_gateway.set_provider(BundleProvider())
    original_run_local = workflow_starter.run_local_revision_rewrite_proposal
    workflow_starter.run_local_revision_rewrite_proposal = lambda job_id: None

    try:
        token, project_id = await _register_with_project(
            client,
            "revision-full-rewrite@example.com",
        )
        await _seed_project_quota(db_session, project_id)

        chat = await client.post(
            f"/api/v1/projects/{project_id}/revisions/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": "整体改成男频校园异能升级流。",
                "mode": "full_project_rewrite",
            },
        )
    finally:
        workflow_starter.run_local_revision_rewrite_proposal = original_run_local

    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["proposals"] == []
    assert body["job"]["job_type"] == "revision_rewrite_proposal"
    assert body["job"]["status"] == "queued"
    assert body["job"]["input_payload"]["revision_session_id"] == body["session"]["id"]
    assert body["job"]["reserved_quota"] == 3000


@pytest.mark.asyncio
async def test_revision_rewrite_proposal_job_creates_bundle_proposal(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services.model_gateway.service import model_gateway
    from app.workflows import activities
    from app.workflows.activities import mark_job_status, revision_rewrite_proposal
    from app.workflows.starter import workflow_starter

    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)
    monkeypatch.setattr(
        workflow_starter,
        "start_revision_rewrite_proposal",
        lambda job: f"test-revision-rewrite-{job['id']}",
    )
    monkeypatch.setattr(workflow_starter, "is_local_workflow", lambda _: False)
    model_gateway.set_provider(BundleProvider())

    token, project_id = await _register_with_project(
        client,
        "revision-rewrite-job@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}
    await _seed_project_quota(db_session, project_id)

    chat = await client.post(
        f"/api/v1/projects/{project_id}/revisions/chat",
        headers=headers,
        json={
            "message": "整体改成男频校园异能升级流。",
            "mode": "full_project_rewrite",
        },
    )
    assert chat.status_code == 200, chat.text
    job_id = chat.json()["job"]["id"]

    await mark_job_status(job_id, "running")
    result = await revision_rewrite_proposal({"id": job_id})
    await mark_job_status(job_id, "succeeded", None, result)

    session_id = chat.json()["session"]["id"]
    session = await client.get(
        f"/api/v1/projects/{project_id}/revisions/sessions/{session_id}",
        headers=headers,
    )
    assert session.status_code == 200, session.text
    proposals = session.json()["proposals"]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["target_type"] == "story_bible_bundle"
    assert proposal["patch"]["story_bible"]["genre"] == "男频校园异能升级流"
    assert proposal["patch"]["story_bible"]["main_characters"][0]["name"] == "许亦舟"

    job = await db_session.get(GenerationJob, job_id)
    assert job is not None
    assert job.status == "succeeded"
    assert job.consumed_quota == 3000
    assert (job.output_payload or {}).get("proposal_ids") == [proposal["id"]]

    calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    assert len(calls) == 1
    assert calls[0].task_type == "revision_rewrite_proposal"


@pytest.mark.asyncio
async def test_apply_story_bible_bundle_updates_assets(client, db_session):
    from app.services.model_gateway.service import model_gateway

    token, project_id = await _register_with_project(
        client,
        "revision-apply-bundle@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}
    model_gateway.set_provider(BundleProvider())
    project = await db_session.get(Project, project_id)
    assert project is not None

    session = RevisionSession(
        id="rev_session_apply_bundle",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="story_bible",
        title="应用完整快照",
        status="active",
    )
    proposal = RevisionProposal(
        id="rev_prop_apply_bundle",
        organization_id=project.organization_id,
        session_id=session.id,
        project_id=project_id,
        target_type="story_bible_bundle",
        action="update",
        title="完整重构",
        reason="测试应用完整快照",
        impact=["story_bible"],
        patch=_bundle_patch(),
        status="pending",
    )
    db_session.add_all([session, proposal])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{proposal.id}/apply",
        headers=headers,
    )

    assert applied.status_code == 200, applied.text
    spec = (
        await db_session.execute(select(NovelSpec).where(NovelSpec.project_id == project_id))
    ).scalar_one()
    assert spec.genre == "男频校园异能升级流"
    characters = (
        (await db_session.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    assert [row.name for row in characters] == ["许亦舟"]
    world_items = (
        (await db_session.execute(select(WorldItem).where(WorldItem.project_id == project_id)))
        .scalars()
        .all()
    )
    assert {row.type for row in world_items} >= {"location", "faction", "rule"}
    threads = (
        (await db_session.execute(select(PlotThread).where(PlotThread.project_id == project_id)))
        .scalars()
        .all()
    )
    assert any("折页界" in row.title for row in threads)


@pytest.mark.asyncio
async def test_apply_story_bible_bundle_with_rebuild_clears_downstream_and_creates_job(
    client,
    db_session,
    monkeypatch,
):
    from app.workflows.starter import workflow_starter

    monkeypatch.setattr(
        workflow_starter,
        "start_generate_full_novel",
        lambda job: f"test-full-novel-{job['id']}",
    )
    monkeypatch.setattr(workflow_starter, "is_local_workflow", lambda _: False)

    token, project_id = await _register_with_project(
        client,
        "revision-rebuild@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None
    org = await db_session.get(Organization, project.organization_id)
    assert org is not None
    assert org.plan_code == "Free"
    now = datetime.now(timezone.utc)
    quota = QuotaBalance(
        id=new_id("quota"),
        organization_id=project.organization_id,
        quota_key="monthly_generated_words",
        period_start=now,
        period_end=now + timedelta(days=30),
        limit_value=100_000,
        used_value=0,
        reserved_value=0,
        reset_at=now + timedelta(days=30),
    )
    chapter = Chapter(
        id="chapter_rebuild_old",
        organization_id=project.organization_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="旧章节",
        summary="旧摘要",
    )
    scene = Scene(
        id="scene_rebuild_old",
        organization_id=project.organization_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="旧场景",
    )
    draft = DraftVersion(
        id="draft_rebuild_old",
        organization_id=project.organization_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        version_type="draft",
        content="旧正文",
        word_count=3,
        status="draft",
        created_by=project.created_by,
    )
    issue = ContinuityIssue(
        id="issue_rebuild_old",
        organization_id=project.organization_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        issue_type="continuity",
        severity="medium",
        description="旧问题",
    )
    memory = MemoryEntry(
        id="memory_rebuild_old",
        organization_id=project.organization_id,
        project_id=project_id,
        source_type="scene",
        source_id=scene.id,
        memory_type="scene_summary",
        title="旧记忆",
        content="旧记忆内容",
    )
    session = RevisionSession(
        id="rev_session_rebuild",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="story_bible",
        title="重构测试",
        status="active",
    )
    proposal = RevisionProposal(
        id="rev_prop_rebuild",
        organization_id=project.organization_id,
        session_id=session.id,
        project_id=project_id,
        target_type="story_bible_bundle",
        action="update",
        title="完整重构",
        reason="测试重构",
        impact=["story_bible", "chapters", "scenes", "drafts"],
        patch=_bundle_patch(),
        status="pending",
    )
    db_session.add_all([quota, chapter, scene, draft, issue, memory, session, proposal])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{proposal.id}/apply-with-rebuild",
        headers=headers,
        json={"estimate_words": 12_000, "scenes_per_chapter": 2, "write_drafts": True},
    )

    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["proposal"]["status"] == "applied"
    assert body["job"]["job_type"] == "full_novel"
    assert body["job"]["plan_code"] == "Free"
    assert body["job"]["input_payload"]["force_regenerate_outline"] is True
    assert body["job"]["input_payload"]["force_regenerate_scenes"] is True
    assert (
        await db_session.execute(select(Chapter).where(Chapter.project_id == project_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(Scene).where(Scene.project_id == project_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(DraftVersion).where(DraftVersion.project_id == project_id))
    ).scalars().all() == []
    assert (
        await db_session.execute(
            select(ContinuityIssue).where(ContinuityIssue.project_id == project_id)
        )
    ).scalars().all() == []
    assert (
        await db_session.execute(select(MemoryEntry).where(MemoryEntry.project_id == project_id))
    ).scalars().all() == []
    jobs = (
        (
            await db_session.execute(
                select(GenerationJob).where(GenerationJob.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(jobs) == 1
    assert jobs[0].reserved_quota == 12_000


@pytest.mark.asyncio
async def test_apply_story_bible_bundle_with_rebuild_rejects_active_job(
    client,
    db_session,
):
    token, project_id = await _register_with_project(
        client,
        "revision-rebuild-conflict@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None
    org = await db_session.get(Organization, project.organization_id)
    assert org is not None
    org.plan_code = "Pro"
    session = RevisionSession(
        id="rev_session_rebuild_conflict",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="story_bible",
        title="重构冲突测试",
        status="active",
    )
    proposal = RevisionProposal(
        id="rev_prop_rebuild_conflict",
        organization_id=project.organization_id,
        session_id=session.id,
        project_id=project_id,
        target_type="story_bible_bundle",
        action="update",
        title="完整重构",
        reason="测试重构冲突",
        impact=["story_bible"],
        patch=_bundle_patch(),
        status="pending",
    )
    active_job = GenerationJob(
        id="job_active_rebuild_conflict",
        organization_id=project.organization_id,
        user_id=project.created_by,
        project_id=project_id,
        job_type="generate_outline",
        status="running",
        priority="queue_pro",
        plan_code="Pro",
        reserved_quota=1000,
        consumed_quota=0,
        input_payload={},
    )
    db_session.add_all([session, proposal, active_job])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{proposal.id}/apply-with-rebuild",
        headers=headers,
        json={"estimate_words": 12_000},
    )

    assert applied.status_code == 409, applied.text
    assert applied.json()["error"]["code"] == "project_has_active_job"
    await db_session.refresh(proposal)
    assert proposal.status == "pending"


@pytest.mark.asyncio
async def test_revision_chat_drops_all_null_standard_patch(client):
    from app.services.model_gateway.service import model_gateway

    class NullPatchProvider:
        async def complete_json(self, **_: object) -> dict:
            return {
                "reply": "已生成优化。",
                "proposals": [
                    {
                        "target_type": "story_bible",
                        "target_id": None,
                        "action": "update",
                        "title": "空修改",
                        "patch": {
                            "premise": None,
                            "theme": None,
                            "genre": None,
                            "tone": None,
                            "target_reader": None,
                            "narrative_pov": None,
                            "style_guide": None,
                            "constraints": None,
                            "continuity_rules": None,
                        },
                        "reason": "模型没有给出真实修改。",
                        "impact": ["story_bible"],
                    }
                ],
            }

        async def complete_text(self, **_: object) -> str:
            return ""

    token, project_id = await _register_with_project(client, "revision-null@example.com")
    model_gateway.set_provider(NullPatchProvider())

    chat = await client.post(
        f"/api/v1/projects/{project_id}/revisions/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "请优化故事圣经。"},
    )

    assert chat.status_code == 200, chat.text
    assert chat.json()["proposals"] == []


@pytest.mark.asyncio
async def test_apply_null_patch_proposal_returns_readable_conflict(client, db_session):
    token, project_id = await _register_with_project(client, "revision-null-apply@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None

    session = RevisionSession(
        id="rev_session_null_patch",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="story_bible",
        title="空修改测试",
        status="active",
    )
    proposal = RevisionProposal(
        id="rev_prop_null_patch",
        organization_id=project.organization_id,
        session_id=session.id,
        project_id=project_id,
        target_type="story_bible",
        target_id=None,
        action="update",
        title="空修改",
        reason="历史坏数据",
        impact=["story_bible"],
        patch={
            "premise": None,
            "theme": None,
            "genre": None,
            "tone": None,
            "target_reader": None,
            "narrative_pov": None,
            "style_guide": None,
            "constraints": None,
            "continuity_rules": None,
        },
        status="pending",
    )
    db_session.add_all([session, proposal])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{proposal.id}/apply",
        headers=headers,
    )

    assert applied.status_code == 409, applied.text
    error = applied.json()["error"]
    assert error["code"] == "revision_patch_empty"
    assert "重新生成 AI 优化" in error["message"]


@pytest.mark.asyncio
async def test_apply_proposal_group_updates_all_targets(client, db_session):
    token, project_id = await _register_with_project(client, "revision-group@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None

    session = RevisionSession(
        id="rev_session_group_success",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="story_bible",
        title="成组应用测试",
        status="active",
    )
    proposals = [
        RevisionProposal(
            id="rev_prop_group_spec",
            organization_id=project.organization_id,
            session_id=session.id,
            project_id=project_id,
            target_type="story_bible",
            target_id=None,
            action="update",
            title="强化主题",
            reason="核心设定变更",
            impact=["world_items"],
            patch={"theme": "成组应用后的主题"},
            group_id="revgrp_success",
            group_title="核心设定与世界规则联动",
            is_primary=True,
            risk_notes=["会改变世界规则解释"],
            status="pending",
        ),
        RevisionProposal(
            id="rev_prop_group_world",
            organization_id=project.organization_id,
            session_id=session.id,
            project_id=project_id,
            target_type="world_item",
            target_id=None,
            action="create",
            title="新增联动规则",
            reason="补足世界规则",
            impact=["story_bible"],
            patch={
                "type": "rule",
                "name": "记忆代价",
                "description": "记忆越珍贵，交换代价越不可逆。",
                "importance": "high",
                "is_hard_rule": True,
            },
            group_id="revgrp_success",
            group_title="核心设定与世界规则联动",
            is_primary=False,
            risk_notes=["会改变世界规则解释"],
            status="pending",
        ),
    ]
    db_session.add_all([session, *proposals])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposal-groups/revgrp_success/apply",
        headers=headers,
    )

    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert len(body["proposals"]) == 2
    assert len(body["applied_change_ids"]) == 2
    assert {p["status"] for p in body["proposals"]} == {"applied"}

    spec = await client.get(f"/api/v1/projects/{project_id}/spec", headers=headers)
    assert spec.json()["theme"] == "成组应用后的主题"
    world_items = await client.get(f"/api/v1/projects/{project_id}/world-items", headers=headers)
    assert any(row["name"] == "记忆代价" for row in world_items.json())


@pytest.mark.asyncio
async def test_apply_proposal_group_rolls_back_when_one_fails(client, db_session):
    token, project_id = await _register_with_project(client, "revision-group-rollback@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None

    chapter = Chapter(
        id="chapter_with_scene_group",
        organization_id=project.organization_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="旧章节",
        summary="旧摘要",
    )
    scene = Scene(
        id="scene_for_group_conflict",
        organization_id=project.organization_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="已有场景",
    )
    session = RevisionSession(
        id="rev_session_group_rollback",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="outline",
        title="回滚测试",
        status="active",
    )
    proposals = [
        RevisionProposal(
            id="rev_prop_group_rollback_spec",
            organization_id=project.organization_id,
            session_id=session.id,
            project_id=project_id,
            target_type="story_bible",
            target_id=None,
            action="update",
            title="不应落库的主题",
            reason="测试回滚",
            impact=["chapters"],
            patch={"theme": "不应被写入"},
            group_id="revgrp_rollback",
            group_title="失败回滚组",
            is_primary=True,
            status="pending",
        ),
        RevisionProposal(
            id="rev_prop_group_rollback_chapter",
            organization_id=project.organization_id,
            session_id=session.id,
            project_id=project_id,
            target_type="chapter",
            target_id=chapter.id,
            action="update",
            title="已有场景章节",
            reason="测试冲突",
            impact=["chapters"],
            patch={"summary": "不应被写入的摘要"},
            group_id="revgrp_rollback",
            group_title="失败回滚组",
            is_primary=False,
            status="pending",
        ),
    ]
    db_session.add_all([chapter, scene, session, *proposals])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposal-groups/revgrp_rollback/apply",
        headers=headers,
    )

    assert applied.status_code == 409, applied.text
    assert applied.json()["error"]["code"] == "chapter_has_scenes"

    spec = await client.get(f"/api/v1/projects/{project_id}/spec", headers=headers)
    assert spec.json()["theme"] != "不应被写入"
    await db_session.refresh(chapter)
    assert chapter.summary == "旧摘要"
    rows = (
        (
            await db_session.execute(
                select(RevisionProposal).where(RevisionProposal.group_id == "revgrp_rollback")
            )
        )
        .scalars()
        .all()
    )
    assert {row.status for row in rows} == {"pending"}


@pytest.mark.asyncio
async def test_apply_chapter_patch_only_without_scenes(client, db_session):
    token, project_id = await _register_with_project(client, "revision-chapter@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None

    chapter = Chapter(
        id="chapter_without_scene",
        organization_id=project.organization_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="旧标题",
        summary="旧摘要",
    )
    session = RevisionSession(
        id="rev_session_chapter",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="chapter",
        title="章节测试",
        status="active",
    )
    proposal = RevisionProposal(
        id="rev_prop_chapter",
        organization_id=project.organization_id,
        session_id=session.id,
        project_id=project_id,
        target_type="chapter",
        target_id=chapter.id,
        action="update",
        title="优化章节",
        reason="强化钩子",
        impact=["chapters"],
        patch={"title": "新标题", "ending_hook": "新的结尾钩子"},
        status="pending",
    )
    db_session.add_all([chapter, session, proposal])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{proposal.id}/apply",
        headers=headers,
    )

    assert applied.status_code == 200, applied.text
    await db_session.refresh(chapter)
    assert chapter.title == "新标题"
    assert chapter.ending_hook == "新的结尾钩子"


@pytest.mark.asyncio
async def test_apply_chapter_patch_with_scenes_returns_conflict(client, db_session):
    token, project_id = await _register_with_project(
        client, "revision-chapter-conflict@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    project = await db_session.get(Project, project_id)
    assert project is not None

    chapter = Chapter(
        id="chapter_with_scene",
        organization_id=project.organization_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=1,
        title="旧标题",
        summary="旧摘要",
    )
    scene = Scene(
        id="scene_for_chapter_conflict",
        organization_id=project.organization_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="已有场景",
    )
    session = RevisionSession(
        id="rev_session_chapter_conflict",
        organization_id=project.organization_id,
        project_id=project_id,
        created_by=project.created_by,
        scope="chapter",
        title="章节冲突测试",
        status="active",
    )
    proposal = RevisionProposal(
        id="rev_prop_chapter_conflict",
        organization_id=project.organization_id,
        session_id=session.id,
        project_id=project_id,
        target_type="chapter",
        target_id=chapter.id,
        action="update",
        title="不安全章节修改",
        reason="测试冲突",
        impact=["chapters"],
        patch={"summary": "不应应用"},
        status="pending",
    )
    db_session.add_all([chapter, scene, session, proposal])
    await db_session.commit()

    applied = await client.post(
        f"/api/v1/projects/{project_id}/revisions/proposals/{proposal.id}/apply",
        headers=headers,
    )

    assert applied.status_code == 409, applied.text
    assert applied.json()["error"]["code"] == "chapter_has_scenes"
