"""Sprint 12-B：full novel orchestrator 集成测试。

测试不依赖真正的 Temporal worker：直接实例化 GenerateFullNovelWorkflow，
通过 monkeypatch 把 `workflow.execute_activity` / `workflow.execute_child_workflow`
/ `workflow.continue_as_new` / `workflow.info` 替换成本地实现，
让 workflow 的编排逻辑在普通 asyncio 事件循环上跑。

verify 内容：
1. happy path：完整 full_novel job → outline 落 N 章 → drafts 落库 → 父 job
   状态 succeeded、reservation consumed、output_payload 含 metrics
2. continue_as_new：4 章 + K=3 batch → 第一 run 处理 1..3 章，第二 run
   处理第 4 章；最终所有章节都有 draft
3. 单章失败隔离：mock writer 在第 2 章抛错 → 其他章节仍正常完成，
   metrics.chapters_failed = 1
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    DraftVersion,
    GenerationJob,
    NovelSpec,
    Organization,
    Project,
    QuotaBalance,
    QuotaReservation,
    Scene,
    User,
)
from app.models.common import new_id
from app.workflows import activities
from app.workflows import generate_full_novel as full_novel_mod
from app.workflows.generate_full_novel import (
    GenerateFullNovelChapterWorkflow,
    GenerateFullNovelWorkflow,
)


class _ContinueAsNewSignal(BaseException):
    """workflow.continue_as_new 的本地化等价物。

    在真 Temporal 上 continue_as_new 会通过专属事件让 server 重新调度同名
    workflow 并把 history 重置；测试里我们改成抛此异常，外层 runner 捕获后
    再次实例化 workflow 并调 run(args)。这样能保留"分批"语义，又不需要
    起 WorkflowEnvironment。
    """

    def __init__(self, args: list[Any]):
        self.args = args


async def _drive_full_novel_workflow(
    monkeypatch,
    Session,
    *,
    job_id: str,
    fail_chapter_ids: set[str] | None = None,
) -> tuple[GenerateFullNovelWorkflow, list[dict[str, Any]]]:
    """把 workflow 模块里的 Temporal API 替换成本地实现，然后驱动
    workflow.run 直到终态（含 continue_as_new 迭代）。

    返回 (最后一次的 workflow 实例, run_records)；run_records 记录了每次
    run 的输入参数，便于断言 continue_as_new 次数。
    """
    fail_chapter_ids = fail_chapter_ids or set()

    # activity 调用：直接 await activity 函数本体，忽略 retry / timeout
    async def fake_execute_activity(activity_fn, *, args, **kwargs):
        return await activity_fn(*args)

    # child workflow 调用：实例化目标类直接 await run(*args)
    async def fake_execute_child_workflow(target, *, args, **kwargs):
        # target 是 Class.run 这种 unbound method；通过 __self_class__/__qualname__
        # 取出 class 后实例化新对象再调用。简化：检测 args[0]['chapter_id']，
        # 若在 fail_chapter_ids 集合内就直接 raise，模拟子 workflow 失败。
        payload = args[0]
        chapter_id = payload.get("chapter_id")
        if chapter_id and chapter_id in fail_chapter_ids:
            raise RuntimeError(f"simulated_chapter_failure:{chapter_id}")
        wf = GenerateFullNovelChapterWorkflow()
        return await wf.run(payload)

    def fake_continue_as_new(*, args):
        raise _ContinueAsNewSignal(args)

    fake_info = SimpleNamespace(
        workflow_id=f"test-wf-{job_id}",
        task_queue="test-queue",
    )

    monkeypatch.setattr(full_novel_mod.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(
        full_novel_mod.workflow, "execute_child_workflow", fake_execute_child_workflow
    )
    monkeypatch.setattr(full_novel_mod.workflow, "continue_as_new", fake_continue_as_new)
    monkeypatch.setattr(full_novel_mod.workflow, "info", lambda: fake_info)
    # workflow.logger 在非 workflow context 内会抛 _NotInWorkflowEventLoopError；
    # 替换成标准 logging.Logger，让 failure path 里的 warning 调用能完成。
    import logging
    monkeypatch.setattr(full_novel_mod.workflow, "logger", logging.getLogger("test.full_novel"))

    job = {"id": job_id}
    run_records: list[dict[str, Any]] = []
    # 模拟分批 run：直到不再 continue_as_new
    current_args: list[Any] = [job, 0, None]
    while True:
        wf = GenerateFullNovelWorkflow()
        run_records.append({"offset": current_args[1] if len(current_args) > 1 else 0})
        try:
            result = await wf.run(*current_args)
            return wf, run_records, result
        except _ContinueAsNewSignal as sig:
            current_args = list(sig.args)


def _make_seed_session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_full_novel_project(
    Session,
    *,
    job_id: str = "job_full_novel_test",
    org_id: str = "org_full_novel_test",
    project_id: str = "project_full_novel_test",
    user_id: str = "user_full_novel_test",
    target_chapters: int = 3,
    scenes_per_chapter: int = 2,
    estimate_words: int = 6000,
    quota_limit: int = 100_000,
    pre_create_chapters: bool = True,
    pre_create_spec: bool = True,
) -> None:
    """统一 setup：org/user/project + 可选的预置 spec/chapters + 父 job +
    quota_balance + quota_reservation。预置 spec/chapters 让 prepare 走
    reuse 分支，避免依赖 LLM mock 行为；测试聚焦 orchestrator 编排逻辑。
    """
    async with Session() as session:
        now = datetime.now(timezone.utc)
        user = User(
            id=user_id,
            email=f"{user_id}@example.com",
            password_hash="x",
            display_name="FullNovelUser",
        )
        org = Organization(
            id=org_id,
            name="FullNovelOrg",
            owner_user_id=user.id,
            plan_code="Pro",
        )
        project = Project(
            id=project_id,
            organization_id=org.id,
            created_by=user.id,
            title="全本生成测试",
            genre="悬疑",
            target_word_count=estimate_words,
            target_chapter_count=target_chapters,
            style="冷峻克制",
        )
        quota_balance = QuotaBalance(
            id=new_id("quota"),
            organization_id=org.id,
            quota_key="monthly_generated_words",
            period_start=now,
            period_end=now + timedelta(days=30),
            limit_value=quota_limit,
            used_value=0,
            reserved_value=estimate_words,
            reset_at=now + timedelta(days=30),
        )
        session.add_all([user, org, project, quota_balance])
        await session.flush()
        if pre_create_spec:
            session.add(
                NovelSpec(
                    id=new_id("spec"),
                    organization_id=org.id,
                    project_id=project.id,
                    premise="一个预置的前提",
                    theme="预置的主题",
                    genre="悬疑",
                )
            )
        if pre_create_chapters:
            project.status = "outlined"
            for idx in range(1, target_chapters + 1):
                session.add(
                    Chapter(
                        id=f"chapter_{idx:02d}_{project.id[:8]}",
                        organization_id=org.id,
                        project_id=project.id,
                        volume_id=None,
                        chapter_index=idx,
                        title=f"第{idx}章",
                        summary=f"第{idx}章摘要",
                        goal=f"目标{idx}",
                        conflict=f"冲突{idx}",
                        ending_hook=f"钩子{idx}",
                        status="planned",
                    )
                )
        job = GenerationJob(
            id=job_id,
            organization_id=org.id,
            user_id=user.id,
            project_id=project.id,
            job_type="full_novel",
            status="queued",
            priority="queue_pro",
            plan_code="Pro",
            reserved_quota=estimate_words,
            consumed_quota=0,
            input_payload={
                "estimate_words": estimate_words,
                "topic": "测试题材",
                "target_chapters": target_chapters,
                "scenes_per_chapter": scenes_per_chapter,
            },
        )
        session.add(job)
        await session.flush()
        session.add(
            QuotaReservation(
                id=new_id("res"),
                organization_id=org.id,
                job_id=job.id,
                quota_key="monthly_generated_words",
                reserved_amount=estimate_words,
                consumed_amount=0,
                status="reserved",
                expires_at=now + timedelta(hours=24),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_full_novel_orchestrator_writes_all_chapters(db_engine, monkeypatch):
    """3 章 + K=3：单 run 内完成所有章节，settle 时把 reservation 消耗。"""
    Session = _make_seed_session_factory(db_engine)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    await _seed_full_novel_project(
        Session,
        job_id="job_happy",
        target_chapters=3,
        scenes_per_chapter=2,
    )

    _, run_records, result = await _drive_full_novel_workflow(
        monkeypatch, Session, job_id="job_happy"
    )

    # 3 章 + K=3 一批跑完，应该只有一次 run（没有 continue_as_new）
    assert len(run_records) == 1
    assert result["status"] == "succeeded"

    async with Session() as session:
        job = await session.get(GenerationJob, "job_happy")
        scenes = (await session.execute(select(Scene))).scalars().all()
        drafts = (await session.execute(select(DraftVersion))).scalars().all()
        reservation = (
            await session.execute(
                select(QuotaReservation).where(QuotaReservation.job_id == "job_happy")
            )
        ).scalar_one()
        quota = (
            await session.execute(
                select(QuotaBalance).where(QuotaBalance.organization_id == job.organization_id)
            )
        ).scalar_one()
        project = await session.get(Project, job.project_id)

    assert job.status == "succeeded"
    payload = job.output_payload or {}
    assert payload["chapters_total"] == 3
    assert payload["chapters_drafted"] == 3
    assert payload["chapters_failed"] == 0
    assert payload["scenes_drafted"] == 6  # 3 章 × 2 scene
    assert payload["scenes_words"] > 0
    assert len(scenes) == 6
    assert len(drafts) == 6
    assert reservation.status == "consumed"
    # 实际写出字数被 commit；commit_quota 用 min(actual, reserved)
    assert quota.used_value > 0
    assert quota.used_value <= job.reserved_quota
    assert quota.reserved_value == 0
    assert project.status == "drafting"


@pytest.mark.asyncio
async def test_full_novel_orchestrator_continues_as_new_across_batches(
    db_engine, monkeypatch
):
    """4 章 + K=3：第一 run 处理 1..3，continue_as_new 触发第二 run 处理第 4
    章；总计 8 scene 全部 drafted。"""
    Session = _make_seed_session_factory(db_engine)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    await _seed_full_novel_project(
        Session,
        job_id="job_can",
        target_chapters=4,
        scenes_per_chapter=2,
        estimate_words=12000,
    )

    _, run_records, result = await _drive_full_novel_workflow(
        monkeypatch, Session, job_id="job_can"
    )

    # 4 章 / batch_size=3：应触发一次 continue_as_new → 共 2 run
    assert [r["offset"] for r in run_records] == [0, 3]
    assert result["status"] == "succeeded"

    async with Session() as session:
        job = await session.get(GenerationJob, "job_can")
        drafts = (await session.execute(select(DraftVersion))).scalars().all()
        chapters = (await session.execute(select(Chapter))).scalars().all()

    assert job.status == "succeeded"
    summary = job.output_payload or {}
    assert summary["chapters_total"] == 4
    assert summary["chapters_drafted"] == 4
    assert summary["chapters_failed"] == 0
    assert summary["scenes_drafted"] == 8
    assert len(drafts) == 8
    # 所有 chapter 应都被推进到 drafted
    assert all(c.status == "drafted" for c in chapters)


@pytest.mark.asyncio
async def test_full_novel_orchestrator_isolates_failing_chapter(
    db_engine, monkeypatch
):
    """让第 2 章的 child workflow 抛错：第 1/3 章仍正常完成，job 整体 succeeded，
    metrics.chapters_failed=1。"""
    Session = _make_seed_session_factory(db_engine)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    await _seed_full_novel_project(
        Session,
        job_id="job_isolate",
        target_chapters=3,
        scenes_per_chapter=2,
    )

    # 锁定第 2 章 id（在 seed 中按 `chapter_{idx:02d}_{project_prefix}` 命名）
    async with Session() as session:
        ch2 = (
            await session.execute(
                select(Chapter).where(Chapter.chapter_index == 2)
            )
        ).scalar_one()
        failing_chapter_id = ch2.id

    _, run_records, result = await _drive_full_novel_workflow(
        monkeypatch,
        Session,
        job_id="job_isolate",
        fail_chapter_ids={failing_chapter_id},
    )

    assert len(run_records) == 1
    assert result["status"] == "succeeded"

    async with Session() as session:
        job = await session.get(GenerationJob, "job_isolate")
        drafts = (await session.execute(select(DraftVersion))).scalars().all()

    summary = job.output_payload or {}
    assert summary["chapters_total"] == 3
    assert summary["chapters_failed"] == 1
    assert failing_chapter_id in summary["failed_chapter_ids"]
    assert summary["chapters_drafted"] == 2  # 1 / 3
    # 第 2 章没有 draft；其他两章各 2 个 scene draft
    assert len(drafts) == 4


@pytest.mark.asyncio
async def test_full_novel_orchestrator_skips_scenes_when_budget_runs_out(
    db_engine, monkeypatch
):
    """父 job reserved 极小，无法覆盖任何 scene 的 target_words：
    应进入 budget skip 路径，job 仍 succeeded 但 metrics.scenes_skipped > 0。
    """
    Session = _make_seed_session_factory(db_engine)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    # 给极小 reserved（500 字）：每场景 target_words 默认 600 → 全部 skip
    await _seed_full_novel_project(
        Session,
        job_id="job_budget",
        target_chapters=2,
        scenes_per_chapter=2,
        estimate_words=2400,  # 不会触发场景跳过：每场景配额=600
    )
    # 直接把 reserved_quota 改到 500，target_words_per_scene 仍按原 estimate
    # 不重算（prepare 内会用 input_payload.estimate_words 算出 600）
    async with Session() as session:
        job = await session.get(GenerationJob, "job_budget")
        job.reserved_quota = 500
        await session.commit()

    _, run_records, result = await _drive_full_novel_workflow(
        monkeypatch, Session, job_id="job_budget"
    )

    assert result["status"] == "succeeded"
    async with Session() as session:
        job = await session.get(GenerationJob, "job_budget")
    summary = job.output_payload or {}
    # 4 个 scene 全部因预算不足而 skipped
    assert summary["scenes_skipped"] >= 1
    assert summary["scenes_drafted"] == 0
    assert summary["chapters_drafted"] == 0
