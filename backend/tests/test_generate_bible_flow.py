from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.common import new_id
from app.models import (
    Character,
    GenerationJob,
    ModelCall,
    NovelSpec,
    PlotThread,
    QuotaBalance,
    QuotaReservation,
    UsageEvent,
    WorldItem,
)
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
async def test_generate_bible_flow_persists_sprint1_records(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    token, org_id = await _register(client, "bible-flow@example.com")
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
    await db_session.commit()

    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "雾城记忆案",
            "genre": "悬疑幻想",
            "target_word_count": 120000,
            "target_chapter_count": 24,
            "style": "冷峻克制",
        },
    )
    assert project_res.status_code == 201, project_res.text
    project_id = project_res.json()["id"]

    generate_res = await client.post(
        f"/api/v1/projects/{project_id}/bible/generate",
        headers=headers,
        json={"estimate_words": 2000, "topic": "记忆交易"},
    )
    assert generate_res.status_code == 202, generate_res.text
    job_id = generate_res.json()["id"]
    assert generate_res.json()["job_type"] == "generate_bible"

    for _ in range(20):
        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        if job and job.status == "succeeded":
            break
        await asyncio.sleep(0.05)

    db_session.expire_all()
    spec = (
        await db_session.execute(select(NovelSpec).where(NovelSpec.project_id == project_id))
    ).scalar_one_or_none()
    characters = (
        await db_session.execute(select(Character).where(Character.project_id == project_id))
    ).scalars().all()
    world_items = (
        await db_session.execute(select(WorldItem).where(WorldItem.project_id == project_id))
    ).scalars().all()
    plot_threads = (
        await db_session.execute(select(PlotThread).where(PlotThread.project_id == project_id))
    ).scalars().all()
    model_calls = (
        await db_session.execute(select(ModelCall).where(ModelCall.job_id == job_id))
    ).scalars().all()
    usage_events = (
        await db_session.execute(select(UsageEvent).where(UsageEvent.job_id == job_id))
    ).scalars().all()
    reservation = (
        await db_session.execute(select(QuotaReservation).where(QuotaReservation.job_id == job_id))
    ).scalar_one_or_none()
    quota = (
        await db_session.execute(
            select(QuotaBalance).where(
                QuotaBalance.organization_id == org_id,
                QuotaBalance.quota_key == "monthly_generated_words",
            )
        )
    ).scalar_one_or_none()
    job = await db_session.get(GenerationJob, job_id)

    assert job is not None
    assert job.status == "succeeded"
    assert job.consumed_quota == 2000
    assert spec is not None
    assert spec.premise
    assert len(characters) >= 2
    assert len(world_items) >= 2
    assert len(plot_threads) >= 1
    assert len(model_calls) >= 1
    assert len(usage_events) == 1
    assert usage_events[0].amount == 2000
    assert reservation is not None
    assert reservation.status == "consumed"
    assert quota is not None
    assert quota.used_value == 2000
    assert quota.reserved_value == 0

    bible_res = await client.get(f"/api/v1/projects/{project_id}/bible", headers=headers)
    assert bible_res.status_code == 200
    bible = bible_res.json()
    assert bible["spec"]["premise"]
    assert len(bible["characters"]) >= 2
    assert len(bible["world_items"]) >= 2
    assert len(bible["plot_threads"]) >= 1
    assert bible["latest_job"]["id"] == job_id
