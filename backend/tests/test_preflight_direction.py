"""preflight + direction preview API 端到端测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.common import new_id
from app.models.quota import QuotaBalance


async def _register_with_project(client, email: str, *, target_chapter_count: int = 5, genre: str = "悬疑"):
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    org_id = res.json()["user"]["organization_id"]
    pres = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Preflight 测试小说",
            "genre": genre,
            "target_chapter_count": target_chapter_count,
            "target_word_count": target_chapter_count * 2000,
            "target_reader": "成人",
            "style": "克制",
        },
    )
    assert pres.status_code in (200, 201), pres.text
    return token, org_id, pres.json()["id"]


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
async def test_preflight_with_sufficient_quota(client, db_engine):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(client, "pf-ok@example.com")
    async with Session() as s:
        await _seed_quota(s, org_id, limit=50000)

    res = await client.get(
        f"/api/v1/projects/{project_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
        params={"job_type": "generate_bible"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["can_generate"] is True
    assert body["estimate_words"] == 2000
    assert body["quota_available"] == 50000
    assert body["is_long_novel"] is False
    # checks 中至少有一条 ok
    levels = [c["level"] for c in body["checks"]]
    assert "ok" in levels
    assert "block" not in levels
    # 状态为 created → next_action 指向生成圣经
    assert body["next_action"]["kind"] == "generate_bible"
    assert body["next_action"]["href_suffix"] == "/bible"


@pytest.mark.asyncio
async def test_preflight_blocks_when_quota_insufficient(client, db_engine):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(client, "pf-poor@example.com")
    # 只给 500 字额度，远小于 generate_bible 预估 2000
    async with Session() as s:
        await _seed_quota(s, org_id, limit=500)

    res = await client.get(
        f"/api/v1/projects/{project_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
        params={"job_type": "generate_bible"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["can_generate"] is False
    blocks = [c for c in body["checks"] if c["level"] == "block"]
    assert blocks, "expect at least one block-level check"


@pytest.mark.asyncio
async def test_preflight_marks_long_novel_warning(client, db_engine):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(
        client, "pf-long@example.com", target_chapter_count=750
    )
    async with Session() as s:
        await _seed_quota(s, org_id, limit=50000)

    res = await client.get(
        f"/api/v1/projects/{project_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
        params={"job_type": "generate_bible"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_long_novel"] is True
    warn_labels = [c["label"] for c in body["checks"] if c["level"] == "warn"]
    assert any("超长篇" in label for label in warn_labels)


@pytest.mark.asyncio
async def test_preflight_blocks_outline_without_bible(client, db_engine):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id, project_id = await _register_with_project(client, "pf-stage@example.com")
    async with Session() as s:
        await _seed_quota(s, org_id, limit=50000)

    res = await client.get(
        f"/api/v1/projects/{project_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
        params={"job_type": "generate_outline"},
    )
    assert res.status_code == 200
    body = res.json()
    # status=created 不允许 generate_outline
    assert body["can_generate"] is False
    assert any("需要先完成故事圣经" in c["label"] for c in body["checks"])


@pytest.mark.asyncio
async def test_direction_preview_returns_three_for_suspense_genre(client):
    token, _, project_id = await _register_with_project(
        client, "dir-sus@example.com", genre="悬疑"
    )
    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/preview-directions",
        headers={"Authorization": f"Bearer {token}"},
        json={"topic": "校园档案室"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["directions"]) == 3
    assert any(d["recommended"] for d in body["directions"])
    # topic 出现在 summary 里
    assert all("校园档案室" in d["summary"] for d in body["directions"])


@pytest.mark.asyncio
async def test_direction_preview_handles_unknown_genre(client):
    token, _, project_id = await _register_with_project(
        client, "dir-unk@example.com", genre="赛博朋克"
    )
    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/preview-directions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert res.status_code == 200
    body = res.json()
    # 未匹配关键字时仍能 fallback 返回 3 个方向
    assert len(body["directions"]) == 3


@pytest.mark.asyncio
async def test_direction_preview_appends_forbidden_themes_into_risk(client):
    token, _, project_id = await _register_with_project(
        client, "dir-forbid@example.com", genre="校园"
    )
    res = await client.post(
        f"/api/v1/projects/{project_id}/bible/preview-directions",
        headers={"Authorization": f"Bearer {token}"},
        json={"forbidden_themes": ["血腥", "政治隐喻"]},
    )
    assert res.status_code == 200
    body = res.json()
    risks = " ".join(d["risk"] for d in body["directions"])
    assert "血腥" in risks
    assert "政治隐喻" in risks
