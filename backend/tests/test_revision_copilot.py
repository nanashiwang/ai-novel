from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import RevisionAppliedChange


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
