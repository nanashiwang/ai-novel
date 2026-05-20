"""验证 generate_chapter_outline / generate_chapter_scene_cards 在 force_regenerate=True
时先删除旧记录、再写新记录，不会追加重复 chapter_index / scene_index。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chapter import Chapter
from app.models.common import new_id
from app.models.generation_job import GenerationJob
from app.models.project import NovelSpec, Project
from app.models.quota import QuotaBalance
from app.workflows import activities


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


@pytest.mark.asyncio
async def test_outline_force_regenerate_replaces_old_chapters(
    client, db_engine, db_session, monkeypatch
):
    """已有 chapters 的项目 force_regenerate 后，旧章节应被删除而��追加。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    token, org_id = await _register(client, "outline-replace@example.com")
    # 让 activity 的 session 工厂复用测试库；monkeypatch 自动还原避免污染其他用例
    import contextlib

    @contextlib.asynccontextmanager
    async def _activity_session():
        async with Session() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    monkeypatch.setattr(activities, "_activity_session", _activity_session)

    headers = {"Authorization": f"Bearer {token}"}
    pres = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "重生成测试",
            "genre": "悬疑",
            "target_chapter_count": 5,
            "target_word_count": 30000,
            "target_reader": "成人",
            "style": "克制",
        },
    )
    project_id = pres.json()["id"]

    now = datetime.now(timezone.utc)
    async with Session() as s:
        # 配 quota（用于 reserve）
        s.add(
            QuotaBalance(
                id=new_id("quota"),
                organization_id=org_id,
                quota_key="monthly_generated_words",
                period_start=now,
                period_end=now + timedelta(days=30),
                limit_value=50000,
                used_value=0,
                reserved_value=0,
                reset_at=now + timedelta(days=30),
            )
        )
        # 必须先有 spec（activity 会 _load_spec）
        s.add(
            NovelSpec(
                id=new_id("spec"),
                organization_id=org_id,
                project_id=project_id,
                premise="测试 premise",
                theme="主题",
                genre="悬疑",
                tone="克制",
                target_reader="成人",
                narrative_pov="第三人称",
                style_guide="克制",
                constraints=[],
                continuity_rules=[],
            )
        )
        # 预先种 3 个旧章节（模拟之前生成过的废柴）
        for i in range(1, 4):
            s.add(
                Chapter(
                    id=new_id("chapter"),
                    organization_id=org_id,
                    project_id=project_id,
                    volume_id=None,
                    chapter_index=i,
                    title=f"旧章节{i}",
                    summary="旧",
                    goal="旧",
                    conflict="旧",
                    ending_hook="旧",
                    status="planned",
                )
            )
        await s.commit()

    # 模拟一个 force_regenerate_outline=True 的 job，绕过 API 直接调 activity
    async with Session() as s:
        job = GenerationJob(
            id=new_id("job"),
            organization_id=org_id,
            user_id="any",
            project_id=project_id,
            job_type="generate_outline",
            status="running",
            priority="queue_free",
            plan_code="Free",
            reserved_quota=3000,
            consumed_quota=0,
            input_payload={
                "estimate_words": 3000,
                "target_chapters": 5,
                "force_regenerate_outline": True,
            },
        )
        s.add(job)
        await s.commit()
        job_id = job.id

    result = await activities.generate_chapter_outline({"id": job_id})
    assert result["reused"] is False

    # 校验：旧"旧章节1/2/3"已被删，新章节 1..5 落库
    async with Session() as s:
        rows = (
            await s.execute(
                select(Chapter).where(Chapter.project_id == project_id).order_by(
                    Chapter.chapter_index.asc()
                )
            )
        ).scalars().all()
    titles = [r.title for r in rows]
    assert len(rows) == 5, f"应是 5 章新章节，实际 {len(rows)}：{titles}"
    assert not any(t.startswith("旧章节") for t in titles), (
        f"旧章节应被删除，但仍在 db：{titles}"
    )
    # chapter_index 应严格 1..5 不重复
    indices = sorted(r.chapter_index for r in rows)
    assert indices == [1, 2, 3, 4, 5], f"index 应为 1..5，实际 {indices}"
