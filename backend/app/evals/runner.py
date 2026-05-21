"""离线评测 Runner。

负责：
- 加载 YAML 数据集
- 对每条样本跑 objective metrics
- 可选：跑 LLM judge（默认 disabled 走 stub）
- 聚合统计 + 输出 JSON 报告到 backend/eval_reports/
"""
from __future__ import annotations

import asyncio
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.evals.judges import JudgmentContract, judge_scene
from app.evals.metrics import compute_all_metrics

# 数据集根目录与报告输出根目录
DATASET_ROOT = Path(__file__).resolve().parent / "datasets"
REPORT_ROOT = Path(__file__).resolve().parents[2] / "eval_reports"

# 章节级 / 全书级评测 TODO：当前 runner 只评 scene。后续如需扩展，应保持
# Sample 与 SampleResult 不变，新增 ChapterSample / BookSample 并在 runner
# 里分发，避免破坏现有 schema。


@dataclass
class Sample:
    """单条评测样本（scene 级）。"""

    id: str
    genre: str
    language: str = "zh"
    bible_summary: str = ""
    chapter_plan: dict[str, Any] = field(default_factory=dict)
    scene_plan: dict[str, Any] = field(default_factory=dict)
    target_words: int = 0
    reference_content: str = ""
    notes: str = ""
    source_path: str = ""


@dataclass
class SampleResult:
    """单条样本的评测结果。"""

    sample_id: str
    genre: str
    objective_metrics: dict[str, Any]
    judge_scores: dict[str, Any]
    judge_aggregate: float


@dataclass
class EvalReport:
    """完整评测报告。"""

    generated_at: str
    dataset_count: int
    judge_disabled: bool
    samples: list[SampleResult]
    aggregate: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def load_sample(path: Path) -> Sample:
    """从 YAML 加载单条样本。字段缺失走 dataclass 默认值。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Sample(
        id=str(raw.get("id") or path.stem),
        genre=str(raw.get("genre") or "unknown"),
        language=str(raw.get("language") or "zh"),
        bible_summary=str(raw.get("bible_summary") or ""),
        chapter_plan=dict(raw.get("chapter_plan") or {}),
        scene_plan=dict(raw.get("scene_plan") or {}),
        target_words=int(raw.get("target_words") or 0),
        reference_content=str(raw.get("reference_content") or ""),
        notes=str(raw.get("notes") or ""),
        source_path=str(path),
    )


def list_dataset_paths(dataset: str = "all") -> list[Path]:
    """根据 dataset 参数返回 YAML 路径列表。

    dataset == "all"：返回 datasets/ 下全部 *.yaml；
    否则视为单个数据集 id 或文件名（兼容 "xuanhuan_01" / "xuanhuan_01.yaml"）。
    """
    if not DATASET_ROOT.exists():
        return []
    if dataset == "all":
        return sorted(DATASET_ROOT.glob("*.yaml"))
    target_names = (dataset, f"{dataset}.yaml")
    return sorted(
        p for p in DATASET_ROOT.glob("*.yaml")
        if p.name in target_names or p.stem == dataset
    )


async def run_eval(
    dataset: str = "all",
    *,
    judge_disabled: bool = True,
    output_dir: Path | None = None,
) -> EvalReport:
    """跑一批样本并返回 EvalReport。

    judge_disabled=True（默认）：跳过 LLM 调用，judge 评分使用 stub。
    output_dir：可选，覆盖默认报告目录（用于测试）。
    """
    paths = list_dataset_paths(dataset)
    samples = [load_sample(p) for p in paths]
    results: list[SampleResult] = []
    for sample in samples:
        objective = compute_all_metrics(sample.reference_content)
        # judge 走 stub 时 session 传 None；判断在 judge_scene 内部完成
        judgment = await judge_scene(
            session=None,
            scene_content=sample.reference_content,
            scene_plan=sample.scene_plan,
            bible_summary=sample.bible_summary,
            disabled=judge_disabled,
        )
        results.append(
            SampleResult(
                sample_id=sample.id,
                genre=sample.genre,
                objective_metrics=objective,
                judge_scores=_judgment_to_dict(judgment),
                judge_aggregate=judgment.aggregate(),
            )
        )
    report = EvalReport(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        dataset_count=len(results),
        judge_disabled=judge_disabled,
        samples=results,
        aggregate=_build_aggregate(results),
    )
    _persist_report(report, output_dir=output_dir)
    return report


def _judgment_to_dict(j: JudgmentContract) -> dict[str, Any]:
    return {
        "coherence": j.coherence,
        "dialogue_naturalness": j.dialogue_naturalness,
        "pacing": j.pacing,
        "show_dont_tell": j.show_dont_tell,
        "comments": j.comments,
        "is_stub": j.is_stub,
    }


def _build_aggregate(results: list[SampleResult]) -> dict[str, Any]:
    """对所有样本做跨样本聚合。

    指标只挑可单值聚合的：dialogue_ratio / lexical_diversity / sensory_total
    / judge_aggregate；其余指标在 per-sample 层级查看即可。
    """
    if not results:
        return {}

    def _values(extractor: Any) -> list[float]:
        return [float(extractor(r)) for r in results]

    dialog = _values(lambda r: r.objective_metrics.get("dialogue_ratio", 0.0))
    lex_div = _values(lambda r: r.objective_metrics.get("lexical_diversity", 0.0))
    sensory = _values(
        lambda r: r.objective_metrics.get("sensory_density", {}).get("total", 0.0)
    )
    judge_agg = _values(lambda r: r.judge_aggregate)

    def _stats(values: list[float]) -> dict[str, float]:
        return {
            "mean": round(statistics.fmean(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    return {
        "dialogue_ratio": _stats(dialog),
        "lexical_diversity": _stats(lex_div),
        "sensory_density_total": _stats(sensory),
        "judge_aggregate": _stats(judge_agg),
    }


def _persist_report(report: EvalReport, *, output_dir: Path | None) -> Path:
    """把报告写入 eval_reports/<timestamp>.json。"""
    target_dir = output_dir or REPORT_ROOT
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = target_dir / f"eval-{stamp}.json"
    path.write_text(report.to_json(), encoding="utf-8")
    return path


def run_eval_sync(
    dataset: str = "all",
    *,
    judge_disabled: bool = True,
    output_dir: Path | None = None,
) -> EvalReport:
    """同步包装，便于 CLI 调用。"""
    return asyncio.run(
        run_eval(dataset, judge_disabled=judge_disabled, output_dir=output_dir)
    )
