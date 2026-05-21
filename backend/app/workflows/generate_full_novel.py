"""全本生成 Orchestrator（Sprint 12-B）。

设计：把 full_novel 拆成"一次只跑 K 章 + continue_as_new 进入下一批"的
分批工作流，避免单条 Temporal workflow 的 history 撑爆（默认 51200 events
/ ~50MB）。

执行结构：

    GenerateFullNovelWorkflow
      ├─ activity: prepare_full_novel
      │   · 创建 NovelSpec（若没有）
      │   · 创建 chapters（若没有），返回升序 chapter_ids
      │
      ├─ 取 chapter_ids[offset : offset+BATCH_SIZE]
      ├─ 对该批的每一章并行启动一个 child workflow:
      │     GenerateFullNovelChapterWorkflow(job_id, chapter_id, ...)
      │       ├─ activity: plan_chapter_scenes_for_full_novel
      │       └─ activity: write_chapter_scenes_for_full_novel
      │
      ├─ 单章失败 (子 workflow 抛异常) → try/except 捕获，记为 failed 不中断
      ├─ 若 chapter_ids 还有未处理章节
      │     → continue_as_new(self.run, {job_id, offset+BATCH_SIZE, prev_metrics})
      ├─ 否则：
      │     activity: finalize_full_novel → settle quota + 写 output_payload
      │     activity: mark_job_status('succeeded')

continue_as_new：父 workflow 用 BATCH_SIZE=3，每批结束后调
`workflow.continue_as_new(self.run, ...)`。这会把当前 workflow 的 history
清零，避免长篇（数百章）时 history 累积导致 worker GetWorkflowHistory 超时
或超 50MB 上限。

quota 估算：父 job 的 reserved_quota = target_chapters × avg_words_per_chapter
（由 API 层在创建 job 时按 estimate_words 决定）。每章实际写出的字数由
`write_chapter_scenes_for_full_novel` 内部累加，最后由 `finalize_full_novel`
在 settle 时一次性 commit 给 quota_service.commit_quota，未写出的章节不
扣额度。preflight：每个 scene 写作前会检查父 job 剩余预算，不够时直接
skipped（不中断后续章节）。
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        finalize_full_novel,
        mark_job_status,
        plan_chapter_scenes_for_full_novel,
        prepare_full_novel,
        write_chapter_scenes_for_full_novel,
    )
    from app.workflows.retry_policy import (
        MODEL_ACTIVITY_RETRY,
        STATUS_ACTIVITY_RETRY,
    )


# 一批同时启动的章节数。3 是任务要求的默认值；可以根据 worker 数量上调。
# 选 3 的考虑：
# - 模型并发：openai/claude 同时跑多个 scene draft，单租户 QPS 通常 < 10
# - history 大小：每章约 30~80 event，3 章 + 同 history 内的 prepare/finalize
#   一起约 200~500 event，远低于 51200 上限
# - 失败放大：1 章失败影响 1 个并发槽，不会让父批整体退化太多
BATCH_SIZE = 3

# 单章 child workflow 的最长执行时间。包含 scene_plan + 多 scene write。
# 给得宽松些（45min），让模型在 P99 时不会因 timeout 误判失败。
CHAPTER_CHILD_TIMEOUT = timedelta(minutes=45)


@workflow.defn
class GenerateFullNovelChapterWorkflow:
    """单章 child workflow。

    每个 chapter 一个独立 workflow execution，让父 workflow 用
    `execute_child_workflow` 并发启动它们。单章失败时只影响自己的子
    workflow，父 workflow 用 try/except 隔离。
    """

    @workflow.run
    async def run(self, args: dict[str, Any]) -> dict[str, Any]:
        job_id = args["job_id"]
        chapter_id = args["chapter_id"]
        scenes_per_chapter = int(args.get("scenes_per_chapter") or 3)
        target_words_per_scene = int(args.get("target_words_per_scene") or 1200)
        expected_words = int(
            args.get("expected_words") or scenes_per_chapter * target_words_per_scene
        )

        plan_result = await workflow.execute_activity(
            plan_chapter_scenes_for_full_novel,
            args=[job_id, chapter_id, scenes_per_chapter, expected_words],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=MODEL_ACTIVITY_RETRY,
        )
        write_result = await workflow.execute_activity(
            write_chapter_scenes_for_full_novel,
            args=[job_id, chapter_id, target_words_per_scene],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=MODEL_ACTIVITY_RETRY,
        )
        return {
            "chapter_id": chapter_id,
            "plan": plan_result,
            "write": write_result,
        }


def _empty_metrics() -> dict[str, Any]:
    return {
        "chapters_total": 0,
        "chapters_drafted": 0,
        "chapters_failed": 0,
        "chapters_skipped": 0,
        "scenes_drafted": 0,
        "scenes_reused": 0,
        "scenes_failed": 0,
        "scenes_skipped": 0,
        "scenes_words": 0,
        "failed_chapter_ids": [],
    }


def _merge_chapter_result(metrics: dict[str, Any], result: dict[str, Any]) -> None:
    write = (result or {}).get("write") or {}
    drafted = int(write.get("scenes_drafted") or 0)
    reused = int(write.get("scenes_reused") or 0)
    skipped = int(write.get("scenes_skipped") or 0)
    words = int(write.get("words") or 0)
    metrics["scenes_drafted"] += drafted
    metrics["scenes_reused"] += reused
    metrics["scenes_skipped"] += skipped
    metrics["scenes_words"] += words
    # 章节判定：所有 scene 都写完 = chapter 成功；否则按 skipped/部分处理
    if drafted + reused > 0 and skipped == 0:
        metrics["chapters_drafted"] += 1
    elif drafted + reused == 0 and skipped > 0:
        metrics["chapters_skipped"] += 1
    else:
        # 写了一部分但还有 skip 的，按 drafted 计（已经产出内容了），
        # 同时 scenes_skipped 已计入。
        metrics["chapters_drafted"] += 1


@workflow.defn
class GenerateFullNovelWorkflow:
    """全本生成父 orchestrator（分批 + continue_as_new）。

    参数：
        job: 父 GenerationJob 的 {id, ...}
        offset: 本次 run 从哪个 chapter_index 开始（continue_as_new 传入）
        prev_metrics: 上一批的累积 metric（continue_as_new 传入）
    """

    @workflow.run
    async def run(
        self,
        job: dict[str, Any],
        offset: int = 0,
        prev_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = job["id"]
        metrics = prev_metrics or _empty_metrics()

        # 第一次进入：把 status 切到 running；continue_as_new 后再次进入时
        # mark_job_status 是幂等的，可以安全反复调用。
        if offset == 0:
            await workflow.execute_activity(
                mark_job_status,
                args=[job_id, "running"],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )

        try:
            preparation = await workflow.execute_activity(
                prepare_full_novel,
                args=[job],
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=MODEL_ACTIVITY_RETRY,
            )
        except Exception as exc:  # noqa: BLE001
            # 准备阶段（生成 spec / outline）失败：整个 full_novel 失败
            await workflow.execute_activity(
                mark_job_status,
                args=[job_id, "failed", f"prepare_failed: {exc!s}"],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            raise

        chapter_ids: list[str] = list(preparation.get("chapter_ids") or [])
        scenes_per_chapter = int(preparation.get("scenes_per_chapter") or 3)
        target_words_per_scene = int(preparation.get("target_words_per_scene") or 1200)
        metrics["chapters_total"] = len(chapter_ids)

        # 本批次要处理的章节窗口
        batch = chapter_ids[offset : offset + BATCH_SIZE]

        # 并发启动一批 child workflow，每章一个；用 gather + return_exceptions
        # 让单章失败不会立刻拖垮整批，父 workflow 自己拿到结果做 try/except。
        async def _run_chapter(chapter_id: str) -> dict[str, Any]:
            return await workflow.execute_child_workflow(
                GenerateFullNovelChapterWorkflow.run,
                args=[
                    {
                        "job_id": job_id,
                        "chapter_id": chapter_id,
                        "scenes_per_chapter": scenes_per_chapter,
                        "target_words_per_scene": target_words_per_scene,
                    }
                ],
                id=f"{workflow.info().workflow_id}-ch-{chapter_id}",
                task_queue=workflow.info().task_queue,
                execution_timeout=CHAPTER_CHILD_TIMEOUT,
            )

        results = await asyncio.gather(
            *[_run_chapter(cid) for cid in batch],
            return_exceptions=True,
        )
        for chapter_id, result in zip(batch, results):
            if isinstance(result, BaseException):
                # 单章子 workflow 失败：记一次 chapters_failed，继续下一章
                # 不 re-raise，让其余批次能完成
                metrics["chapters_failed"] += 1
                metrics["failed_chapter_ids"].append(chapter_id)
                workflow.logger.warning(
                    "full_novel_chapter_failed",
                    extra={"chapter_id": chapter_id, "error": str(result)},
                )
                continue
            _merge_chapter_result(metrics, result)

        next_offset = offset + BATCH_SIZE
        # 还有未处理章节 → continue_as_new 切到下一批，让 history 重置
        if next_offset < len(chapter_ids):
            workflow.continue_as_new(args=[job, next_offset, metrics])

        # 所有章节处理完毕：finalize + mark succeeded
        try:
            summary = await workflow.execute_activity(
                finalize_full_novel,
                args=[job_id, metrics],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
        except Exception as exc:  # noqa: BLE001
            await workflow.execute_activity(
                mark_job_status,
                args=[job_id, "failed", f"finalize_failed: {exc!s}"],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=STATUS_ACTIVITY_RETRY,
            )
            raise

        await workflow.execute_activity(
            mark_job_status,
            args=[job_id, "succeeded", None, summary],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=STATUS_ACTIVITY_RETRY,
        )
        return {"job_id": job_id, "status": "succeeded", "result": summary}
