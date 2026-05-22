from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    Chapter,
    Character,
    Project,
    RevisionAppliedChange,
    RevisionProposal,
    RevisionSession,
    Scene,
)


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
        change.after_data.get("theme") == "记忆交易背后的代价与自我选择"
        for change in changes
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
        await db_session.execute(
            select(RevisionProposal).where(RevisionProposal.group_id == "revgrp_rollback")
        )
    ).scalars().all()
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
