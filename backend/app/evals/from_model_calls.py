"""消费 model_calls 历史按 variant 聚合评测（Sprint 15-D2）。

D1 已经把命中 A/B 实验的调用结果写到 `model_calls.metadata_json.experiment_id`
与 `variant`。本模块加载这些行，提取响应内容，跑客观指标，按 variant 聚合，
输出对比报告。

设计：
- 输入：experiment_id（必填）+ 可选时间窗
- 跨方言策略：拉所有候选 model_calls → 在 Python 端按 metadata 过滤
  （SQLite 和 PG 都行；上量后可改 JSON path 函数）
- 内容提取：
  * 优先 response_json["content"]（SceneDraftContract / 大部分 generate_json）
  * 兜底 response_text（generate_text 路径）
  * 都空时跳过该行
- 聚合：每个 variant 输出 sample_count + 客观指标均值 + 与对手的 delta
- 不调 LLM judge（CI 跑得起 + 数据规模大时太贵）；judge 仍走 stub 时返 3.0
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evals.metrics import compute_all_metrics
from app.models.model_call import ModelCall


@dataclass
class VariantSample:
    """单次 model_calls 抽样后的指标。"""

    call_id: str
    project_id: str | None
    task_type: str
    prompt_version: str
    content_length: int
    objective_metrics: dict[str, Any]


@dataclass
class VariantAggregate:
    """单个 variant 的跨样本聚合。"""

    variant: str
    sample_count: int
    objective: dict[str, float]


@dataclass
class ExperimentComparison:
    """A vs B 对比报告。"""

    experiment_id: str
    generated_at: str
    total_calls: int
    matched_calls: int
    variants: dict[str, VariantAggregate]
    deltas: dict[str, float] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "generated_at": self.generated_at,
            "total_calls": self.total_calls,
            "matched_calls": self.matched_calls,
            "variants": {k: asdict(v) for k, v in self.variants.items()},
            "deltas": self.deltas,
            "notes": self.notes,
        }


def _extract_content(call: ModelCall) -> str:
    """从 model_calls 行中拿出"可评测的正文字符串"。

    优先 response_json["content"]（SceneDraftContract 的 content 字段）；
    其次 response_text；都空返 ""。
    """
    if call.response_json:
        content = call.response_json.get("content")
        if isinstance(content, str) and content.strip():
            return content
    if call.response_text and call.response_text.strip():
        return call.response_text
    return ""


def _objective_summary(metrics_list: list[dict[str, Any]]) -> dict[str, float]:
    """对多次评测的客观指标做均值聚合。

    只挑可单值聚合的关键指标：dialogue_ratio / lexical_diversity /
    sensory_density.total / paragraph_count / sentence_length.mean。
    """
    if not metrics_list:
        return {}

    def _avg(extract) -> float:
        values = [float(extract(m) or 0.0) for m in metrics_list]
        return round(sum(values) / max(1, len(values)), 4)

    return {
        "dialogue_ratio": _avg(lambda m: m.get("dialogue_ratio")),
        "lexical_diversity": _avg(lambda m: m.get("lexical_diversity")),
        "sensory_density_total": _avg(
            lambda m: (m.get("sensory_density") or {}).get("total")
        ),
        "paragraph_count": _avg(lambda m: m.get("paragraph_count")),
        "sentence_length_mean": _avg(
            lambda m: (m.get("sentence_length") or {}).get("mean")
        ),
    }


async def compare_experiment(
    session: AsyncSession,
    *,
    experiment_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    sample_limit: int = 500,
) -> ExperimentComparison:
    """加载 experiment_id 对应的 model_calls 并对比 A/B 两个 variant。

    sample_limit 防失控：单实验最多消费 500 条调用。
    """
    stmt = select(ModelCall).order_by(ModelCall.created_at.asc())
    if since is not None:
        stmt = stmt.where(ModelCall.created_at >= since)
    if until is not None:
        stmt = stmt.where(ModelCall.created_at <= until)
    stmt = stmt.limit(sample_limit)
    rows = list((await session.execute(stmt)).scalars().all())

    by_variant: dict[str, list[VariantSample]] = {"a": [], "b": []}
    for call in rows:
        meta = call.metadata_json or {}
        if meta.get("experiment_id") != experiment_id:
            continue
        variant = meta.get("variant")
        if variant not in by_variant:
            continue
        content = _extract_content(call)
        if not content:
            continue
        metrics = compute_all_metrics(content)
        by_variant[variant].append(
            VariantSample(
                call_id=call.id,
                project_id=call.project_id,
                task_type=call.task_type,
                prompt_version=call.prompt_version,
                content_length=len(content),
                objective_metrics=metrics,
            )
        )

    variants: dict[str, VariantAggregate] = {}
    for variant_label, samples in by_variant.items():
        variants[variant_label] = VariantAggregate(
            variant=variant_label,
            sample_count=len(samples),
            objective=_objective_summary([s.objective_metrics for s in samples]),
        )

    deltas: dict[str, float] = {}
    a_obj = variants["a"].objective
    b_obj = variants["b"].objective
    for key in a_obj.keys() | b_obj.keys():
        deltas[key] = round(b_obj.get(key, 0.0) - a_obj.get(key, 0.0), 4)

    matched = variants["a"].sample_count + variants["b"].sample_count
    return ExperimentComparison(
        experiment_id=experiment_id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total_calls=len(rows),
        matched_calls=matched,
        variants=variants,
        deltas=deltas,
        notes=(
            "deltas = variant_b - variant_a。值 > 0 表示 B 在该指标上高于 A；"
            "结合 prompt 语义与 multi-agent 成本综合判断胜出。"
        ),
    )
