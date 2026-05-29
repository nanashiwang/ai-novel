"""BatchRunner 单元测试（Sprint 17-E）。

验证：
1. 跨章并发受 Semaphore 限制
2. 同章 scenes 严格按 scene_index 串行
3. 单项失败不阻断其他项
4. 进度持久化到 batch_job.output_payload
"""
from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.generation_job import GenerationJob
from app.services.generation import batch_service
from app.services.generation.batch_service import BatchRunner, BatchTarget


@pytest_asyncio.fixture
async def batch_job_row(
    db_engine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> GenerationJob:
    # 让 BatchRunner._save_progress 使用测试 SQLite engine 而非全局生产 engine
    TestSession = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(batch_service, "AsyncSessionLocal", TestSession)

    job = GenerationJob(
        id="batch_job_test_1",
        organization_id="org_test",
        user_id="user_test",
        project_id="proj_test",
        job_type="batch_scene_write",
        status="running",
        priority="queue_standard",
        plan_code="Pro",
        reserved_quota=0,
        consumed_quota=0,
        input_payload={},
        output_payload={},
    )
    db_session.add(job)
    await db_session.commit()
    return job


async def test_cross_chapter_concurrency_capped(batch_job_row: GenerationJob) -> None:
    """3 章并发上限 = 3：第 4 章必须等到任一章释放才能进入临界区。"""
    runner = BatchRunner(max_chapter_concurrency=3, progress_save_every=10)
    targets = [
        BatchTarget(target_id=f"scene_c{c}", chapter_id=f"chap_{c}", chapter_index=c, scene_index=1)
        for c in range(1, 6)
    ]

    in_flight: list[int] = []
    max_in_flight = 0
    lock = asyncio.Lock()

    async def handler(target: BatchTarget, _job: GenerationJob) -> dict:
        nonlocal max_in_flight
        async with lock:
            in_flight.append(target.chapter_index)
            max_in_flight = max(max_in_flight, len(in_flight))
        await asyncio.sleep(0.05)
        async with lock:
            in_flight.remove(target.chapter_index)
        return {"ok": True}

    result = await runner.run(
        batch_job_id=batch_job_row.id,
        organization_id=batch_job_row.organization_id,
        project_id=batch_job_row.project_id,
        batch_type="scene_write",
        targets=targets,
        handler=handler,  # type: ignore[arg-type]
    )

    assert result["total_items"] == 5
    assert result["completed_items"] == 5
    assert result["failed_items"] == 0
    assert max_in_flight <= 3, f"跨章并发峰值 {max_in_flight} 超过 3"


async def test_same_chapter_serial_order(batch_job_row: GenerationJob) -> None:
    """同章 scenes 必须按 scene_index 升序串行：scene 2 的 start 时间 > scene 1 的 end。"""
    runner = BatchRunner(max_chapter_concurrency=3, progress_save_every=10)
    targets = [
        BatchTarget(target_id="s1", chapter_id="c1", chapter_index=1, scene_index=1),
        BatchTarget(target_id="s2", chapter_id="c1", chapter_index=1, scene_index=2),
        BatchTarget(target_id="s3", chapter_id="c1", chapter_index=1, scene_index=3),
    ]
    timeline: list[tuple[str, str, float]] = []

    async def handler(target: BatchTarget, _job: GenerationJob) -> dict:
        timeline.append((target.target_id, "start", time.monotonic()))
        await asyncio.sleep(0.02)
        timeline.append((target.target_id, "end", time.monotonic()))
        return {}

    await runner.run(
        batch_job_id=batch_job_row.id,
        organization_id=batch_job_row.organization_id,
        project_id=batch_job_row.project_id,
        batch_type="scene_write",
        targets=targets,
        handler=handler,  # type: ignore[arg-type]
    )

    starts = {tid: ts for tid, kind, ts in timeline if kind == "start"}
    ends = {tid: ts for tid, kind, ts in timeline if kind == "end"}
    assert starts["s2"] >= ends["s1"], "s2 必须在 s1 结束后才能开始"
    assert starts["s3"] >= ends["s2"], "s3 必须在 s2 结束后才能开始"


async def test_single_item_failure_does_not_block_others(batch_job_row: GenerationJob) -> None:
    """处理器抛错的目标被记入 failed_items，其余仍正常完成。"""
    runner = BatchRunner(
        max_chapter_concurrency=3,
        progress_save_every=10,
        max_item_attempts=2,
        item_retry_initial_delay_seconds=0,
    )
    targets = [
        BatchTarget(target_id="ok1", chapter_id="cA", chapter_index=1, scene_index=1),
        BatchTarget(target_id="bad", chapter_id="cA", chapter_index=1, scene_index=2),
        BatchTarget(target_id="ok2", chapter_id="cB", chapter_index=2, scene_index=1),
    ]

    async def handler(target: BatchTarget, _job: GenerationJob) -> dict:
        if target.target_id == "bad":
            raise RuntimeError("boom")
        return {"target": target.target_id}

    result = await runner.run(
        batch_job_id=batch_job_row.id,
        organization_id=batch_job_row.organization_id,
        project_id=batch_job_row.project_id,
        batch_type="scene_write",
        targets=targets,
        handler=handler,  # type: ignore[arg-type]
    )

    assert result["total_items"] == 3
    assert result["completed_items"] == 2
    assert result["failed_items"] == 1
    by_target = {r["target_id"]: r for r in result["results"]}
    assert by_target["bad"]["status"] == "failed"
    assert by_target["bad"]["error"] == "boom"
    assert by_target["bad"]["attempts"] == 2
    assert by_target["ok1"]["status"] == "succeeded"
    assert by_target["ok2"]["status"] == "succeeded"


async def test_transient_item_failure_retries_and_succeeds(
    batch_job_row: GenerationJob,
) -> None:
    """单项临时失败时自动重试，重试成功后不计入 failed_items。"""
    runner = BatchRunner(
        max_chapter_concurrency=1,
        progress_save_every=1,
        max_item_attempts=3,
        item_retry_initial_delay_seconds=0,
    )
    attempts: dict[str, int] = {}
    targets = [BatchTarget(target_id="flaky", chapter_id="c1", chapter_index=1, scene_index=1)]

    async def handler(target: BatchTarget, _job: GenerationJob) -> dict:
        attempts[target.target_id] = attempts.get(target.target_id, 0) + 1
        if attempts[target.target_id] == 1:
            raise RuntimeError("temporary")
        return {"ok": True}

    result = await runner.run(
        batch_job_id=batch_job_row.id,
        organization_id=batch_job_row.organization_id,
        project_id=batch_job_row.project_id,
        batch_type="scene_write",
        targets=targets,
        handler=handler,  # type: ignore[arg-type]
    )

    assert result["completed_items"] == 1
    assert result["failed_items"] == 0
    item = result["results"][0]
    assert item["status"] == "succeeded"
    assert item["attempts"] == 2
    assert item["result"] == {"ok": True}


async def test_progress_persisted_to_output_payload(
    db_session: AsyncSession, batch_job_row: GenerationJob
) -> None:
    """运行结束后 batch_job.output_payload 含完整进度字段。"""
    runner = BatchRunner(max_chapter_concurrency=2, progress_save_every=1)
    targets = [
        BatchTarget(target_id=f"s{i}", chapter_id="c1", chapter_index=1, scene_index=i)
        for i in range(1, 4)
    ]

    async def handler(target: BatchTarget, _job: GenerationJob) -> dict:
        return {"id": target.target_id}

    await runner.run(
        batch_job_id=batch_job_row.id,
        organization_id=batch_job_row.organization_id,
        project_id=batch_job_row.project_id,
        batch_type="scene_write",
        targets=targets,
        handler=handler,  # type: ignore[arg-type]
    )

    await db_session.refresh(batch_job_row)
    payload = batch_job_row.output_payload or {}
    assert payload.get("batch_type") == "scene_write"
    assert payload.get("total_items") == 3
    assert payload.get("completed_items") == 3
    assert payload.get("failed_items") == 0
    assert "finished_at" in payload
    assert isinstance(payload.get("child_jobs"), list)
    assert len(payload["child_jobs"]) == 3


@pytest.mark.parametrize("batch_size", [0])
async def test_empty_targets_short_circuits(
    db_session: AsyncSession, batch_job_row: GenerationJob, batch_size: int
) -> None:
    """空 targets 直接落进度并返回 0/0/0，不调用 handler。"""
    runner = BatchRunner()
    called = False

    async def handler(_t: BatchTarget, _j: GenerationJob) -> dict:
        nonlocal called
        called = True
        return {}

    result = await runner.run(
        batch_job_id=batch_job_row.id,
        organization_id=batch_job_row.organization_id,
        project_id=batch_job_row.project_id,
        batch_type="scene_write",
        targets=[],
        handler=handler,  # type: ignore[arg-type]
    )
    assert result["total_items"] == 0
    assert not called
