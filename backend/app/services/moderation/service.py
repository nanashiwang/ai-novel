"""Moderation 内容审查服务（Sprint 13-A3）。

目标：在长篇小说生成与用户输入路径上叠加一层内容安全审查，捕获暴力 /
色情 / 自残 / 违禁词等高风险内容，避免 LLM 输出未经过滤直接落库。

设计：
- 主线本地词典 + 正则（zero-dep，永远可用）
- 可选 OpenAI moderation provider（settings.moderation_provider="openai" + openai_api_key）
- 输出统一 `ModerationResult`：flagged / categories / severity / snippets
- 不阻断写入：service 层只产出结果，集成方根据 severity 决定行为
- 集成方式优先 fire-and-forget，单条目失败不影响主流程

KISS：暂不引入数据库表，违规记录走结构化日志 + 事件总线；未来如需
后台可视化再升级到 moderation_records 表。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import get_settings

_logger = logging.getLogger(__name__)

Severity = Literal["none", "low", "medium", "high"]

# ---------------------------------------------------------------------------
# 本地规则：每个 category 给出关键词正则。命中即视为该 category 出现。
# 严重度通过 _CATEGORY_SEVERITY 映射；不同 category 命中后取 max。
# 词库故意保持极简，目的是给出可见的兜底；真实生产建议外置到配置或 KV。
# ---------------------------------------------------------------------------
_RULES: dict[str, list[str]] = {
    "violence": [
        r"砍杀", r"屠戮", r"血腥(?:屠杀|肢解)", r"碎尸", r"肢解",
    ],
    "sexual": [
        r"露骨性爱", r"未成年.*?(?:性|淫)", r"性虐待", r"乱伦",
    ],
    "self_harm": [
        r"自杀方法", r"如何自残", r"上吊步骤", r"割腕",
    ],
    "hate": [
        r"种族.*?灭绝", r"屠杀.*?民族",
    ],
    "illicit": [
        r"制毒方法", r"如何制造.*?毒品", r"炸弹配方", r"枪支制造",
    ],
}

_CATEGORY_SEVERITY: dict[str, Severity] = {
    "violence": "medium",
    "sexual": "high",
    "self_harm": "high",
    "hate": "high",
    "illicit": "high",
}

_COMPILED_RULES: dict[str, list[re.Pattern[str]]] = {
    cat: [re.compile(p, flags=re.IGNORECASE) for p in patterns]
    for cat, patterns in _RULES.items()
}


@dataclass(frozen=True)
class ModerationResult:
    """单次审查输出。

    - flagged：任一规则命中即 True
    - categories：命中的分类列表
    - severity：综合严重度（none/low/medium/high）
    - snippets：命中片段（最多 5 条，便于排障）
    - provider：实际生效的 provider 名（"local" / "openai" / "local+openai"）
    """

    flagged: bool
    categories: list[str] = field(default_factory=list)
    severity: Severity = "none"
    snippets: list[str] = field(default_factory=list)
    provider: str = "local"


def _severity_rank(sev: Severity) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3}[sev]


def _scan_local(text: str) -> tuple[list[str], list[str], Severity]:
    """本地规则扫描。返回 (categories, snippets, severity)。"""
    hit_categories: list[str] = []
    snippets: list[str] = []
    severity: Severity = "none"
    for category, patterns in _COMPILED_RULES.items():
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            if category not in hit_categories:
                hit_categories.append(category)
            # 截取命中位置前后各 20 字便于人工复核
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            if len(snippets) < 5:
                snippets.append(text[start:end])
            cat_sev = _CATEGORY_SEVERITY.get(category, "low")
            if _severity_rank(cat_sev) > _severity_rank(severity):
                severity = cat_sev
            break  # 单 category 命中一次即可
    return hit_categories, snippets, severity


class ModerationService:
    """对外统一入口。"""

    async def check(self, text: str) -> ModerationResult:
        settings = get_settings()
        if not text or not text.strip() or not settings.moderation_enabled:
            return ModerationResult(flagged=False)

        local_cats, local_snips, local_sev = _scan_local(text)
        provider = "local"

        # 可选 OpenAI moderation 叠加
        openai_cats: list[str] = []
        openai_sev: Severity = "none"
        if settings.moderation_provider == "openai" and settings.openai_api_key:
            try:
                openai_cats, openai_sev = await self._openai_check(text, settings)
                provider = "local+openai" if local_cats else "openai"
            except Exception:  # noqa: BLE001
                _logger.warning("moderation_openai_failed", exc_info=True)

        merged_cats = list({*local_cats, *openai_cats})
        merged_sev: Severity = (
            local_sev
            if _severity_rank(local_sev) >= _severity_rank(openai_sev)
            else openai_sev
        )
        flagged = bool(merged_cats)
        return ModerationResult(
            flagged=flagged,
            categories=merged_cats,
            severity=merged_sev if flagged else "none",
            snippets=local_snips,
            provider=provider,
        )

    async def _openai_check(self, text: str, settings) -> tuple[list[str], Severity]:
        """调 OpenAI moderation API。失败由外层捕获回落 local。"""
        import httpx  # noqa: PLC0415

        url = settings.openai_base_url.rstrip("/") + "/moderations"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={"model": "omni-moderation-latest", "input": text[:4000]},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        result = (data.get("results") or [{}])[0]
        categories = result.get("categories") or {}
        scores = result.get("category_scores") or {}
        hit = [c for c, on in categories.items() if on]
        # OpenAI 不给 severity；用最高分映射粗略档：>0.7 high, >0.3 medium
        peak = max((scores.get(c, 0.0) for c in hit), default=0.0)
        sev: Severity = "high" if peak > 0.7 else ("medium" if peak > 0.3 else "low")
        return hit, sev if hit else "none"

    def check_sync(self, text: str) -> ModerationResult:
        """同步包装，仅供 fire-and-forget 调度方使用（如已在事件循环则切异步）。"""
        try:
            return asyncio.run(self.check(text))
        except RuntimeError as exc:
            # 已在 loop 内：调用方应直接 await check()
            raise RuntimeError(
                "check_sync called inside running loop; use check() instead"
            ) from exc


moderation_service = ModerationService()


def log_moderation_event(
    result: ModerationResult,
    *,
    organization_id: str | None = None,
    project_id: str | None = None,
    scene_id: str | None = None,
    source: str = "write_scene",
) -> None:
    """将 moderation 结果落到结构化日志。

    KISS：v1 不写数据库表，依靠日志聚合（loki/elk）即可排查；后续若
    管理后台需要展示，再补 moderation_records 表与查询接口。
    """
    if not result.flagged:
        return
    _logger.warning(
        "moderation_flagged",
        extra={
            "organization_id": organization_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "source": source,
            "categories": result.categories,
            "severity": result.severity,
            "snippets": result.snippets,
            "provider": result.provider,
        },
    )
