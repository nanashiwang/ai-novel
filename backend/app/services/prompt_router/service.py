"""Prompt A/B 分流路由（Sprint 15-D1）。

设计目标：
- ModelGateway 调用入口处问一句"对这个 prompt_key 当前有 active 实验吗？"
- 有的话按 (organization_id, project_id) 做稳定哈希分流，返回应用的 prompt_version
- 实验信息（experiment_id / variant）会被记到 model_calls.metadata_json，
  评测 runner 后续按 variant 聚合就能算出 A/B 胜负

稳定性约束：
- 同一 (experiment, org, project) 多次 route 必须返回同一 variant
  → 用 sha256(f"{experiment_id}:{org_id}:{project_id}") 取模分流
- 没有 project_id（如 admin 操作）时 fallback 到 org_id 维度

缓存（KISS）：
- 进程内 dict + 60s TTL，按 (organization_id, prompt_key) 缓存"当前 active
  实验"查询结果。生产环境单实例够用；多实例 + 频繁切实验时升级到 redis 缓存
- 缓存只缓存"实验存在 / 不存在"，不缓存 variant 路由结果（路由是 pure function）
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_experiment import PromptExperiment

_CACHE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class RoutingResult:
    """对外返回的分流结果。

    - experiment_id / variant 非空时表示命中 A/B 实验，调用方应把它们写到
      model_calls.metadata_json
    - prompt_version 是最终生效的版本（命中实验时已被覆盖；未命中时透传 baseline）
    - original_version 仅当 prompt_version != baseline 时填写，便于事后追溯
    """

    prompt_version: str
    experiment_id: Optional[str] = None
    variant: Optional[str] = None  # "a" | "b"
    original_version: Optional[str] = None


class PromptRouter:
    def __init__(self) -> None:
        # 结构：{(org_id, prompt_key): (cached_experiment_or_none, expires_at)}
        self._cache: dict[tuple[str, str], tuple[Optional[PromptExperiment], float]] = {}

    def _cache_key(self, organization_id: str, prompt_key: str) -> tuple[str, str]:
        return (organization_id or "", prompt_key or "")

    async def _load_active_experiment(
        self,
        session: AsyncSession,
        organization_id: str,
        prompt_key: str,
    ) -> Optional[PromptExperiment]:
        """读 active 实验。同一 (org, prompt_key) 只允许一个 active。

        如果数据库里出现多个 active（管理失误），按 created_at desc 取最新；
        其余视为应该被人工 paused 的孤儿。
        """
        cache_key = self._cache_key(organization_id, prompt_key)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and cached[1] > now:
            return cached[0]

        stmt = (
            select(PromptExperiment)
            .where(
                PromptExperiment.organization_id == organization_id,
                PromptExperiment.prompt_key == prompt_key,
                PromptExperiment.status == "active",
            )
            .order_by(PromptExperiment.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        exp = result.scalar_one_or_none()
        self._cache[cache_key] = (exp, now + _CACHE_TTL_SECONDS)
        return exp

    def invalidate(self, organization_id: str | None = None) -> None:
        """实验状态变更（draft→active / active→paused 等）时调用。

        不传 organization_id 时清空全局缓存；传入时只清该 org。
        """
        if organization_id is None:
            self._cache.clear()
            return
        for key in list(self._cache.keys()):
            if key[0] == organization_id:
                del self._cache[key]

    @staticmethod
    def _bucket(experiment_id: str, organization_id: str, project_id: str | None) -> int:
        """把 (experiment, org, project) 哈希到 [0, 100)。

        sha256 前 8 字节 → uint64 → mod 100。同一组输入必返同值，
        不同输入分布近似均匀（chi-square OK for 10k 项目）。
        """
        seed = f"{experiment_id}:{organization_id}:{project_id or ''}"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()[:8]
        return int.from_bytes(digest, "big") % 100

    async def route(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        prompt_key: str,
        baseline_version: str,
        project_id: str | None = None,
    ) -> RoutingResult:
        """主入口。返回 RoutingResult 给 ModelGateway 消费。

        没有 active 实验 → 透传 baseline_version、experiment_id/variant 为空。
        命中实验 → 按哈希分到 A 或 B，返回对应版本。
        """
        if not prompt_key or not organization_id:
            return RoutingResult(prompt_version=baseline_version)

        exp = await self._load_active_experiment(session, organization_id, prompt_key)
        if exp is None:
            return RoutingResult(prompt_version=baseline_version)

        # split_pct 表示 variant_a 的占比；落入 [0, split) → A，[split, 100) → B
        raw_split = exp.traffic_split_pct
        split = max(0, min(100, int(raw_split if raw_split is not None else 50)))
        bucket = self._bucket(exp.id, organization_id, project_id)
        if bucket < split:
            variant = "a"
            version = exp.variant_a_version
        else:
            variant = "b"
            version = exp.variant_b_version

        return RoutingResult(
            prompt_version=version,
            experiment_id=exp.id,
            variant=variant,
            original_version=baseline_version if version != baseline_version else None,
        )


prompt_router = PromptRouter()
