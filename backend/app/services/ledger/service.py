"""信息释放 ledger service（Sprint 14-C5）。

集成入口：``ledger_service.validate_reveal(session, project_id, scene,
draft_content)`` —— 给定一个 scene 的最新 draft 正文，扫描 secret 类目里
是否有"事实关键词"被命中。如果命中：

1. 检查 scene.characters 是否在 fact.owners ∪ fact.disclosed_to 中。
2. 不在 → 视为"信息泄露"，产出一条 ``Violation``。

KISS：v1 用简单的子串匹配，配合 fact 文本里的「关键短语」抽取，做最快的
兜底。后续 (1) 给 fact 字段加 keyword 列；(2) 引入 LLM 语义识别，再升级
这里的匹配策略。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene import Scene
from app.repositories import InformationLedgerRepository

Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Violation:
    """单条信息泄露违规。

    - fact_id：触发违规的 ledger 行 id
    - severity：综合 fact.importance + status 给出三档
    - description：人类可读的诊断（前端 / 日志均可用）
    """

    fact_id: str
    severity: Severity
    description: str


@dataclass(frozen=True)
class ValidationReport:
    """validate_reveal 的聚合结果。

    返回 list 还是 dataclass：当前调用方只关心 list[Violation]，但留一个
    包装类型方便未来扩展（例如累计扫描了多少 fact、命中了哪些 owners）。
    """

    violations: list[Violation] = field(default_factory=list)
    scanned_count: int = 0


# fact 字符串里识别关键短语的简单规则：
# 1) 中文「」或西文 "" 内的内容（最高优先级，作者显式标注）
# 2) "是X" / "真名叫X" / "X 的真实身份" 这类模式 —— v1 不强求，等 v2 再补
_QUOTE_PATTERNS = [
    re.compile(r"「([^「」\n]{2,40})」"),
    re.compile(r"“([^“”\n]{2,40})”"),
    re.compile(r"\"([^\"\n]{2,40})\""),
]


def _extract_keywords(fact: str) -> list[str]:
    """从 fact 文本里抽取「关键短语」用于在 draft 里命中。

    优先取引号内文本；没有引号时取 fact 本身作为兜底关键词（去掉常见的
    "X 的真实身份是"、"真凶就是" 这类引导语过于宽泛，先不做特殊处理）。
    """
    keywords: list[str] = []
    for pat in _QUOTE_PATTERNS:
        keywords.extend(match.group(1).strip() for match in pat.finditer(fact))
    # 去重且保序
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw and kw not in seen:
            seen.add(kw)
            unique.append(kw)
    if unique:
        return unique
    # 兜底：fact 本身整体匹配（不切词，避免误伤）
    stripped = fact.strip()
    return [stripped] if 2 <= len(stripped) <= 80 else []


def _classify_severity(importance: int) -> Severity:
    """importance ∈ [1,5] → severity；越重要的事实泄露越严重。"""
    if importance >= 4:
        return "high"
    if importance >= 3:
        return "medium"
    return "low"


class LedgerService:
    async def validate_reveal(
        self,
        session: AsyncSession,
        *,
        project_id: str,
        scene: Scene,
        draft_content: str,
    ) -> list[Violation]:
        """扫描 draft 中是否泄露了不该被该场景角色知道的 secret 事实。

        判定规则：
        - 仅处理 ledger.status == 'secret' 的事实（partial/public 都按已经
          开始释放处理，不再视为泄露）。
        - 从 fact 抽关键词，draft_content 命中即视为"读者已被告知"。
        - 命中后判断 scene.characters 是否存在于
          owners ∪ disclosed_to。两边都没有 → 触发违规。
        - 同一条 fact 一次场景最多产出一条 Violation，避免重复报警。
        """
        if not draft_content:
            return []
        repo = InformationLedgerRepository(session)
        rows = list(
            await repo.list(
                organization_id=scene.organization_id,
                project_id=project_id,
                status="secret",
                limit=200,
            )
        )
        if not rows:
            return []

        scene_actors = {name.strip() for name in (scene.characters or []) if name}
        violations: list[Violation] = []
        for row in rows:
            keywords = _extract_keywords(row.fact)
            hit_keyword: str | None = next(
                (kw for kw in keywords if kw and kw in draft_content),
                None,
            )
            if not hit_keyword:
                continue
            authorized = set(row.owners or []) | set(row.disclosed_to or [])
            if scene_actors and scene_actors & authorized:
                # 场景内至少一个出场角色拥有该事实，认为合理
                continue
            severity = _classify_severity(row.importance or 3)
            violations.append(
                Violation(
                    fact_id=row.id,
                    severity=severity,
                    description=(
                        f"Secret fact \"{hit_keyword}\" leaked in scene "
                        f"{scene.id}: actors={sorted(scene_actors)} not in "
                        f"owners={list(row.owners or [])} ∪ "
                        f"disclosed_to={list(row.disclosed_to or [])}"
                    ),
                )
            )
        return violations


ledger_service = LedgerService()


__all__ = [
    "LedgerService",
    "Violation",
    "ValidationReport",
    "ledger_service",
]
