from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    DraftVersion,
    GenerationJob,
    ModelCall,
    NovelSpec,
    Organization,
    Project,
    Scene,
    User,
)
from app.workflows import activities


@pytest.mark.asyncio
async def test_full_novel_pipeline_persists_goat_style_layers(db_engine, monkeypatch):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    async with Session() as session:
        user = User(
            id="user_pipeline",
            email="pipeline@example.com",
            password_hash="x",
            display_name="Pipeline",
        )
        org = Organization(
            id="org_pipeline",
            name="pipeline org",
            owner_user_id=user.id,
            plan_code="Pro",
        )
        project = Project(
            id="project_pipeline",
            organization_id=org.id,
            created_by=user.id,
            title="雾城档案",
            genre="悬疑",
            target_word_count=12000,
            target_chapter_count=3,
            style="冷峻克制",
            target_reader="都市悬疑读者",
        )
        job = GenerationJob(
            id="job_pipeline",
            organization_id=org.id,
            user_id=user.id,
            project_id=project.id,
            job_type="full_novel",
            status="queued",
            priority="queue_pro",
            plan_code="Pro",
            reserved_quota=12000,
            consumed_quota=0,
            input_payload={
                "topic": "雾城里的记忆走私案",
                "estimate_words": 9000,
                "target_chapters": 3,
                "scenes_per_chapter": 2,
            },
        )
        session.add_all([user, org, project, job])
        await session.commit()

    result = await activities.run_full_novel_pipeline({"id": "job_pipeline"})

    assert result["book_spec"]["spec_id"].startswith("spec_")
    assert result["chapters"]["chapter_count"] == 3
    assert result["scenes"]["scene_count"] == 6
    assert result["drafts"]["draft_count"] == 6

    async with Session() as session:
        spec_count = await session.scalar(
            select(NovelSpec).where(NovelSpec.project_id == "project_pipeline")
        )
        chapters = (await session.execute(select(Chapter))).scalars().all()
        scenes = (await session.execute(select(Scene))).scalars().all()
        drafts = (await session.execute(select(DraftVersion))).scalars().all()
        calls = (await session.execute(select(ModelCall))).scalars().all()
        project = await session.get(Project, "project_pipeline")

    assert spec_count is not None
    assert len(chapters) == 3
    assert len(scenes) == 6
    assert len(drafts) == 6
    assert {call.task_type for call in calls} >= {
        "generate_story_bible",
        "plan_chapters",
        "plan_scenes",
        "write_scene_draft",
    }
    assert project is not None
    assert project.current_word_count > 0


@pytest.mark.asyncio
async def test_local_workflow_runs_after_commit(monkeypatch, db_session):
    from datetime import datetime, timedelta, timezone

    from app.models.common import new_id
    from app.models.quota import QuotaBalance
    from app.services.generation.service import generation_service
    from app.workflows.starter import workflow_starter

    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        workflow_starter,
        "start_generate_full_novel",
        lambda job: f"local-generate-full-novel-{job['id']}",
    )
    monkeypatch.setattr(
        workflow_starter,
        "is_local_workflow",
        lambda workflow_id: str(workflow_id).startswith("local-"),
    )
    monkeypatch.setattr(
        workflow_starter,
        "run_local_generate_full_novel",
        lambda job_id: calls.append(("full_novel", job_id)),
    )

    user = User(
        id="user_after_commit",
        email="after-commit@example.com",
        password_hash="x",
        display_name="AfterCommit",
    )
    org = Organization(
        id="org_after_commit",
        name="after commit org",
        owner_user_id=user.id,
        plan_code="Team",
    )
    project = Project(
        id="project_after_commit",
        organization_id=org.id,
        created_by=user.id,
        title="提交后生成",
        target_word_count=1000,
        target_chapter_count=1,
    )
    now = datetime.now(timezone.utc)
    quota = QuotaBalance(
        id=new_id("quota"),
        organization_id=org.id,
        quota_key="monthly_generated_words",
        period_start=now,
        period_end=now + timedelta(days=30),
        limit_value=10000,
        used_value=0,
        reserved_value=0,
        reset_at=now + timedelta(days=30),
    )
    db_session.add_all([user, org, project, quota])
    await db_session.flush()

    tenant = type(
        "Tenant",
        (),
        {
            "organization_id": org.id,
            "organization_name": org.name,
            "plan_code": org.plan_code,
            "organization_role": "owner",
        },
    )()
    current_user = type("CurrentUser", (), {"id": user.id, "platform_role": "user"})()

    job = await generation_service.create_full_novel_job(
        db_session,
        current_user,
        tenant,
        project_id=project.id,
        estimate_words=1000,
        target_chapters=1,
        scenes_per_chapter=1,
    )
    assert db_session.sync_session.info["after_commit_tasks"] == [("full_novel", job.id)]

    await db_session.commit()

    assert calls == [("full_novel", job.id)]
