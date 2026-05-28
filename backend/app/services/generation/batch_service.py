"""批量任务调度器（Sprint 17-E）。

封装"按章分组 → 跨章并发 → 同章串行 → SSE 实时推送"通用调度逻辑。
5 种批量任务（scene_plan / scene_write / audit / rewrite / polish）共用此
runner，只在"如何处理单个 target"层面分支。

设计：
- 不创建子 GenerationJob 行（避免父 / 子 job 状态机复杂化），直接在 batch
  父 job 的 output_payload 内逐项更新进度
- asyncio.Semaphore(N) 控跨章并发；同章 scenes 用顺序 for 循环
- 单项失败 swallow + 计入 failed_items，不阻断其他项
- 每完成一项 publish SSE batch_job.item_completed 事件 → 前端实时更新
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.database import AsyncSessionLocal
from app.models.generation_job import GenerationJob
from app.services.event_bus import build_event, publish_event_fire_and_forget

_logger = logging.getLogger(__name__)


@dataclass
class BatchTarget:
    """单个批量目标项。target_id 是 chapter_id（plan/polish）或 scene_id
    （write/audit/rewrite），由 batch_type 决定语义。"""

    target_id: str
    chapter_id: str | None = None
    chapter_index: int | None = None
    scene_index: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# 单项处理器函数签名：(target, parent_job) -> dict（结果摘要）
# 必须自管 session（独立 AsyncSessionLocal），自管 commit/rollback
TargetHandler = Callable[[BatchTarget, GenerationJob], "asyncio.Future[dict[str, Any]]"]


class BatchRunner:
    """通用批量调度器。"""

    def __init__(
        self,
        *,
        max_chapter_concurrency: int = 3,
        progress_save_every: int = 1,
    ) -> None:
        self.max_chapter_concurrency = max_chapter_concurrency
        self.progress_save_every = progress_save_every

    async def run(
        self,
        *,
        batch_job_id: str,
        organization_id: str,
        project_id: str,
        batch_type: str,
        targets: list[BatchTarget],
        handler: TargetHandler,
    ) -> dict[str, Any]:
        """执行批量任务。

        - targets 按 chapter_id 分组，跨章 asyncio.gather + Semaphore(N)
        - 同章 scenes 串行执行（保证 _previous_scene_excerpt 可用）
        - 每完成一项推 SSE 事件 + 持久化 progress
        """
        channel = f"project:{project_id}"
        total = len(targets)
        if total == 0:
            await self._save_progress(
                batch_job_id=batch_job_id,
                organization_id=organization_id,
                payload={
                    "batch_type": batch_type,
                    "total_items": 0,
                    "completed_items": 0,
                    "failed_items": 0,
                    "running_items": 0,
                    "queued_items": 0,
                    "child_jobs": [],
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            publish_event_fire_and_forget(
                channel,
                build_event(
                    "batch_job.completed",
                    {
                        "batch_job_id": batch_job_id,
                        "batch_type": batch_type,
                        "total_items": 0,
                        "completed_items": 0,
                        "failed_items": 0,
                    },
                ),
            )
            return {
                "total_items": 0,
                "completed_items": 0,
                "failed_items": 0,
            }

        # 按 chapter_id 分组；plan/polish 类 chapter_id == target_id，
        # write/audit/rewrite 类 target_id 是 scene_id，chapter_id 来自 target.chapter_id
        chapter_groups: dict[str, list[BatchTarget]] = {}
        for t in targets:
            grp_key = t.chapter_id or t.target_id
            chapter_groups.setdefault(grp_key, []).append(t)

        # 章内按 scene_index 升序，保证 _previous_scene_excerpt 顺序可用
        for grp in chapter_groups.values():
            grp.sort(key=lambda x: (x.scene_index or 0, x.target_id))

        sem = asyncio.Semaphore(self.max_chapter_concurrency)
        results: list[dict[str, Any]] = []
        completed_count = 0
        failed_count = 0
        running_set: set[str] = set()
        lock = asyncio.Lock()

        publish_event_fire_and_forget(
            channel,
            build_event(
                "batch_job.started",
                {
                    "batch_job_id": batch_job_id,
                    "batch_type": batch_type,
                    "total_items": total,
                    "chapter_count": len(chapter_groups),
                },
            ),
        )

        async def _process_chapter(chap_key: str, group: list[BatchTarget]) -> None:
            nonlocal completed_count, failed_count
            async with sem:
                for target in group:
                    async with lock:
                        running_set.add(target.target_id)
                    publish_event_fire_and_forget(
                        channel,
                        build_event(
                            "batch_job.item_started",
                            {
                                "batch_job_id": batch_job_id,
                                "batch_type": batch_type,
                                "target_id": target.target_id,
                                "chapter_id": target.chapter_id,
                                "chapter_index": target.chapter_index,
                                "scene_index": target.scene_index,
                            },
                        ),
                    )
                    item_status = "succeeded"
                    item_error: str | None = None
                    item_result: dict[str, Any] = {}
                    try:
                        item_result = await handler(target, None)  # type: ignore[arg-type]
                    except Exception as exc:  # noqa: BLE001
                        _logger.warning(
                            "batch_item_failed",
                            exc_info=True,
                            extra={
                                "batch_job_id": batch_job_id,
                                "target_id": target.target_id,
                            },
                        )
                        item_status = "failed"
                        item_error = str(exc) or exc.__class__.__name__
                    async with lock:
                        running_set.discard(target.target_id)
                        if item_status == "succeeded":
                            completed_count += 1
                        else:
                            failed_count += 1
                        results.append(
                            {
                                "target_id": target.target_id,
                                "chapter_id": target.chapter_id,
                                "chapter_index": target.chapter_index,
                                "scene_index": target.scene_index,
                                "status": item_status,
                                "error": item_error,
                                "result": item_result,
                            }
                        )
                    publish_event_fire_and_forget(
                        channel,
                        build_event(
                            f"batch_job.item_{item_status}",
                            {
                                "batch_job_id": batch_job_id,
                                "batch_type": batch_type,
                                "target_id": target.target_id,
                                "chapter_id": target.chapter_id,
                                "chapter_index": target.chapter_index,
                                "scene_index": target.scene_index,
                                "completed_items": completed_count,
                                "failed_items": failed_count,
                                "total_items": total,
                                "error": item_error,
                            },
                        ),
                    )
                    # 节流持久化：每 progress_save_every 项保存一次
                    if (completed_count + failed_count) % max(
                        1, self.progress_save_every
                    ) == 0:
                        await self._save_progress(
                            batch_job_id=batch_job_id,
                            organization_id=organization_id,
                            payload=self._compute_progress(
                                batch_type=batch_type,
                                total=total,
                                completed=completed_count,
                                failed=failed_count,
                                running=list(running_set),
                                results=results,
                            ),
                        )

        await asyncio.gather(
            *(_process_chapter(k, g) for k, g in chapter_groups.items()),
            return_exceptions=False,
        )

        final_payload = self._compute_progress(
            batch_type=batch_type,
            total=total,
            completed=completed_count,
            failed=failed_count,
            running=[],
            results=results,
        )
        final_payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        await self._save_progress(
            batch_job_id=batch_job_id,
            organization_id=organization_id,
            payload=final_payload,
        )
        publish_event_fire_and_forget(
            channel,
            build_event(
                "batch_job.completed",
                {
                    "batch_job_id": batch_job_id,
                    "batch_type": batch_type,
                    "total_items": total,
                    "completed_items": completed_count,
                    "failed_items": failed_count,
                },
            ),
        )
        return {
            "total_items": total,
            "completed_items": completed_count,
            "failed_items": failed_count,
            "results": results,
        }

    @staticmethod
    def _compute_progress(
        *,
        batch_type: str,
        total: int,
        completed: int,
        failed: int,
        running: list[str],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        finished = completed + failed
        return {
            "batch_type": batch_type,
            "total_items": total,
            "completed_items": completed,
            "failed_items": failed,
            "running_items": len(running),
            "queued_items": max(0, total - finished - len(running)),
            "running_target_ids": running,
            "child_jobs": results,
        }

    @staticmethod
    async def _save_progress(
        *,
        batch_job_id: str,
        organization_id: str,
        payload: dict[str, Any],
    ) -> None:
        """把 progress 写到 batch_job.output_payload。独立 session 提交。"""
        try:
            async with AsyncSessionLocal() as session:
                job = await session.get(GenerationJob, batch_job_id)
                if job is None:
                    return
                if job.organization_id != organization_id:
                    return
                # 合并 payload 与已有内容，便于保留 created_at 等元数据
                existing = dict(job.output_payload or {})
                existing.update(payload)
                job.output_payload = existing
                await session.commit()
        except Exception:  # noqa: BLE001
            _logger.warning("batch_progress_save_failed", exc_info=True)


batch_runner = BatchRunner()


__all__ = ["BatchRunner", "BatchTarget", "batch_runner"]
