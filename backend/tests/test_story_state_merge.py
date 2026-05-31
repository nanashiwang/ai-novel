from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    Chapter,
    ChapterStateRequirement,
    ContinuityIssue,
    StoryStateHistory,
    StoryStateItem,
)
from app.models.common import new_id


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": email.split("@")[0],
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_story_state_duplicate_candidates_and_merge(client, db_session):
    token, org_id = await _register(client, "state-merge@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "关键设定合并测试", "target_word_count": 100_000},
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=org_id,
        project_id=project_id,
        volume_id=None,
        chapter_index=12,
        title="青冥洗瞳",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    target = StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="character",
        entity_id="lin_zhaoye",
        state_type="skill",
        name="因果灰线视野",
        status="active",
        summary="林照夜能短暂看见因果灰线，过度使用会左眼刺痛。",
        value_json={"cost": "left_eye_pain"},
        source_chapter_id=chapter.id,
        source_scene_id=None,
        source_excerpt="灰线浮现，左眼刺痛。",
        updated_in_chapter_id=chapter.id,
        priority=80,
        is_hard_constraint=False,
    )
    duplicate = StoryStateItem(
        id=new_id("state"),
        organization_id=org_id,
        project_id=project_id,
        entity_type="character",
        entity_id="lin_zhaoye",
        state_type="skill",
        name="因果灰线",
        status="active",
        summary="因果灰线能力可用于看穿丹药因果，但会带来眼部代价。",
        value_json={"usage": "trace_causality"},
        source_chapter_id=chapter.id,
        source_scene_id=None,
        source_excerpt="因果灰线缠绕毒丹。",
        updated_in_chapter_id=chapter.id,
        priority=95,
        is_hard_constraint=True,
    )
    requirement = ChapterStateRequirement(
        id=new_id("state_req"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        target_chapter_id=chapter.id,
        state_item_id=duplicate.id,
        requirement_type="must_remember",
        summary="本章必须承接因果灰线的眼部代价。",
        priority=90,
        origin_type="manual",
    )
    issue = ContinuityIssue(
        id=new_id("issue"),
        organization_id=org_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_id=None,
        story_state_item_id=duplicate.id,
        issue_type="state_conflict",
        severity="high",
        description="正文把因果灰线写成无代价能力。",
        suggested_fix="合并重复关键设定并保留代价。",
        status="open",
    )
    db_session.add_all([chapter, target, duplicate, requirement, issue])
    await db_session.commit()

    duplicate_res = await client.get(
        f"/api/v1/projects/{project_id}/story-states/duplicate-candidates",
        headers=headers,
        params={"threshold": 70},
    )
    assert duplicate_res.status_code == 200, duplicate_res.text
    groups = duplicate_res.json()["groups"]
    assert groups
    assert groups[0]["anchor"]["id"] == duplicate.id
    assert groups[0]["candidates"][0]["state"]["id"] == target.id
    assert groups[0]["candidates"][0]["score"] >= 70

    merge_res = await client.post(
        f"/api/v1/projects/{project_id}/story-states/{target.id}/merge",
        headers=headers,
        json={
            "source_state_ids": [duplicate.id],
            "summary": "因果灰线视野可看见因果线，早期使用会引发左眼刺痛。",
            "reason": "人工确认两条关键设定重复，合并为同一能力。",
        },
    )
    assert merge_res.status_code == 200, merge_res.text
    merged = merge_res.json()
    assert merged["target"]["id"] == target.id
    assert merged["target"]["summary"] == "因果灰线视野可看见因果线，早期使用会引发左眼刺痛。"
    assert merged["target"]["priority"] == 95
    assert merged["target"]["is_hard_constraint"] is True
    assert merged["target"]["value_json"]["cost"] == "left_eye_pain"
    assert merged["target"]["value_json"]["usage"] == "trace_causality"
    assert merged["merged_ids"] == [duplicate.id]
    assert merged["updated_requirement_count"] == 1
    assert merged["updated_issue_count"] == 1

    source_res = await client.get(
        f"/api/v1/projects/{project_id}/story-states/{duplicate.id}",
        headers=headers,
    )
    assert source_res.status_code == 200, source_res.text
    source = source_res.json()
    assert source["status"] == "inactive"
    assert source["superseded_by_state_id"] == target.id
    assert source["status_reason"] == "人工确认两条关键设定重复，合并为同一能力。"

    await db_session.refresh(requirement)
    await db_session.refresh(issue)
    assert requirement.state_item_id == target.id
    assert issue.story_state_item_id == target.id

    history_rows = (
        await db_session.execute(
            select(StoryStateHistory).where(StoryStateHistory.project_id == project_id)
        )
    ).scalars().all()
    assert {row.state_item_id for row in history_rows} == {target.id, duplicate.id}
