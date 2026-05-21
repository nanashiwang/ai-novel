from __future__ import annotations

import pytest

from app.models import Chapter
from app.models.common import new_id


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_list_chapters_orders_by_chapter_index(client, db_session):
    token, org_id = await _register(client, "chapters-order@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "章节排序测试", "target_word_count": 30000},
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    for chapter_index in [3, 1, 2]:
        db_session.add(
            Chapter(
                id=new_id("chapter"),
                organization_id=org_id,
                project_id=project_id,
                volume_id=None,
                chapter_index=chapter_index,
                title=f"第{chapter_index}章",
                summary="",
                goal="",
                conflict="",
                ending_hook="",
                status="planned",
            )
        )
    await db_session.commit()

    res = await client.get(f"/api/v1/projects/{project_id}/chapters", headers=headers)
    assert res.status_code == 200, res.text
    assert [row["chapter_index"] for row in res.json()] == [1, 2, 3]
