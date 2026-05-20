"""Plot Thread CRUD + NovelSpec.continuity_rules + bible 创作偏好参数。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.common import new_id
from app.models.quota import QuotaBalance


async def _register_with_project(client, email: str):
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    org_id = res.json()["user"]["organization_id"]
    project_res = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "测试小说",
            "genre": "悬疑",
            "target_chapter_count": 5,
            "target_word_count": 30000,
            "target_reader": "成人读者",
            "style": "克制",
        },
    )
    assert project_res.status_code in (200, 201), project_res.text
    return token, org_id, project_res.json()["id"]


async def _seed_quota(db_session: AsyncSession, org_id: str, limit: int = 50000) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        QuotaBalance(
            id=new_id("quota"),
            organization_id=org_id,
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


@pytest.mark.asyncio
async def test_plot_thread_crud(client):
    token, _, project_id = await _register_with_project(client, "thread@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    empty = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads", headers=headers
    )
    assert empty.status_code == 200
    assert empty.json() == []

    created = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        headers=headers,
        json={
            "title": "记忆失窃案",
            "thread_type": "main",
            "description": "主角追查家人记忆消失",
            "related_characters": ["林澈"],
        },
    )
    assert created.status_code == 201
    thread = created.json()
    assert thread["title"] == "记忆失窃案"
    assert thread["status"] == "open"

    patched = await client.patch(
        f"/api/v1/projects/{project_id}/plot-threads/{thread['id']}",
        headers=headers,
        json={"status": "closed", "description": "已揭示真相"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "closed"
    assert patched.json()["description"] == "已揭示真相"
    assert patched.json()["title"] == "记忆失窃案"

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/plot-threads/{thread['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204

    after = await client.get(
        f"/api/v1/projects/{project_id}/plot-threads", headers=headers
    )
    assert after.json() == []


@pytest.mark.asyncio
async def test_novel_spec_supports_continuity_rules(client):
    token, _, project_id = await _register_with_project(client, "spec@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.put(
        f"/api/v1/projects/{project_id}/spec",
        headers=headers,
        json={
            "premise": "测试 premise",
            "theme": "测试主题",
            "constraints": ["不能逆转因果"],
            "continuity_rules": ["主角的记忆不能凭空恢复"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["constraints"] == ["不能逆转因果"]
    assert body["continuity_rules"] == ["主角的记忆不能凭空恢复"]


@pytest.mark.asyncio
async def test_generate_bible_accepts_creative_prefs(client, db_engine):
    """带创作偏好的 generate-bible 请求应被接受，且与不带偏好的请求 dedupe 不同。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(client, "prefs@example.com")
    async with Session() as s:
        await _seed_quota(s, org_id)
    headers = {"Authorization": f"Bearer {token}"}

    res1 = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 1500, "force_regenerate": False},
    )
    assert res1.status_code == 202, res1.text
    job1_id = res1.json()["id"]

    res2 = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={
            "estimate_words": 1500,
            "force_regenerate": False,
            "protagonist_archetype": "一个孤独的档案管理员",
            "reference_works": ["东方快车谋杀案"],
            "forbidden_themes": ["血腥"],
            "temperature": 0.5,
        },
    )
    assert res2.status_code == 202, res2.text
    job2_id = res2.json()["id"]
    assert job1_id != job2_id, "带创作偏好应触发独立 job 而非 dedupe 复用"


@pytest.mark.asyncio
async def test_mock_bible_varies_by_project_title():
    """不同 project.title 在 mock provider 下应生成不同的 premise / 角色名。"""
    from app.services.model_gateway.service import _MockProvider

    mock = _MockProvider()
    p1_prompt = (
        "项目标题：雾城记忆案\n类型：悬疑幻想\n目标读者：中文读者\n文风：克制\n"
        "初始题材/topic：雾城记忆案\n"
    )
    p2_prompt = (
        "项目标题：星海贫民窟\n类型：太空歌剧\n目标读者：中文读者\n文风：粗粝\n"
        "初始题材/topic：星海贫民窟\n"
    )
    bible1 = await mock.complete_json(
        model="m",
        system_prompt="",
        user_prompt=p1_prompt,
        schema={"properties": {"main_characters": {}, "premise": {}}},
        temperature=0.7,
    )
    bible2 = await mock.complete_json(
        model="m",
        system_prompt="",
        user_prompt=p2_prompt,
        schema={"properties": {"main_characters": {}, "premise": {}}},
        temperature=0.7,
    )
    assert bible1["genre"] == "悬疑幻想"
    assert bible2["genre"] == "太空歌剧"
    assert bible1["premise"] != bible2["premise"]
    assert bible1["main_characters"][0]["name"] != bible2["main_characters"][0]["name"]


@pytest.mark.asyncio
async def test_mock_bible_honors_forbidden_themes():
    """禁忌主题应该出现在 constraints 中，作为对 LLM 的硬约束。"""
    from app.services.model_gateway.service import _MockProvider

    mock = _MockProvider()
    prompt = (
        "项目标题：玄幻测试\n类型：玄幻\n目标读者：成人\n文风：豪迈\n"
        "初始题材/topic：玄幻测试\n禁忌主题（绝对不要出现）：血腥, 政治隐喻\n"
    )
    bible = await mock.complete_json(
        model="m",
        system_prompt="",
        user_prompt=prompt,
        schema={"properties": {"main_characters": {}, "premise": {}}},
        temperature=0.7,
    )
    joined = " ".join(bible["constraints"])
    assert "血腥" in joined
    assert "政治隐喻" in joined

