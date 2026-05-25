"""评测 CI gate（Sprint 15-D3）。

把 `app.evals.runner.run_eval` 包装为"评测 + 对比 baseline + 退化时非 0 退出"
的 CI 友好入口。

用法：
  python -m app.evals.ci_gate
  python -m app.evals.ci_gate --baseline path/to/baseline.json --threshold 0.05

设计原则（KISS / YAGNI）：
- baseline 是手动维护的 JSON 快照，commit 到仓库（首次跑无 baseline 时只创建不阻断）
- 退化阈值默认 ±5%：客观指标（dialogue_ratio / lexical_diversity / sensory_density_total）
  相对 baseline 跌幅超过阈值即视为 regression
- 不消费 LLM judge（避免 CI 跑 LLM 成本与不确定性）
- 退出码：0 = 通过，1 = 退化，2 = baseline 缺失（仅警告，首次允许）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.evals.runner import run_eval

DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "eval_baseline.json"
DEFAULT_THRESHOLD = 0.05  # 5% 退化容忍

# 关键指标白名单：方向 "down" 表示"越小越退化"（如 lexical_diversity），
# "up" 表示"越大越退化"（如 target_overshoot_ratio：字数偏差越大越糟）。
# 其它指标作为���考输出，不参与 gate。
_GUARDED_KEYS: dict[str, str] = {
    "dialogue_ratio": "down",
    "lexical_diversity": "down",
    "sensory_density_total": "down",
    "target_overshoot_ratio": "up",
}


def _load_baseline(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _check_regression(
    current_agg: dict[str, Any],
    baseline_agg: dict[str, Any],
    threshold: float,
) -> list[str]:
    """对比 current 与 baseline 的 aggregate.<key>.mean，返回违例描述列表。"""
    violations: list[str] = []
    for key, direction in _GUARDED_KEYS.items():
        cur = ((current_agg or {}).get(key) or {}).get("mean")
        base = ((baseline_agg or {}).get(key) or {}).get("mean")
        if cur is None or base is None:
            continue
        if direction == "down":
            # 越小越退化：越界 = (base - cur) / base > threshold
            if base == 0:
                continue
            delta_pct = (cur - base) / base
            if delta_pct < -threshold:
                violations.append(
                    f"{key} 退化：current={cur:.4f} vs baseline={base:.4f} "
                    f"(下降 {abs(delta_pct):.2%}，阈值 {threshold:.0%})"
                )
        else:  # "up": 越大越退化
            # 越界 = (cur - base) > threshold（绝对差），适合 ratio/percentage 指标
            if cur - base > threshold:
                violations.append(
                    f"{key} 退化：current={cur:.4f} vs baseline={base:.4f} "
                    f"(上升 {cur - base:.4f}，阈值 +{threshold:.0%})"
                )
    return violations


async def _run(
    dataset: str,
    baseline_path: Path,
    threshold: float,
    update_baseline: bool,
) -> int:
    report = await run_eval(dataset=dataset, judge_disabled=True)
    print(f"[eval-ci] samples={report.dataset_count}")
    print(f"[eval-ci] aggregate={json.dumps(report.aggregate, ensure_ascii=False)}")

    baseline = _load_baseline(baseline_path)
    if baseline is None:
        if update_baseline:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(
                json.dumps(
                    {"dataset": dataset, "aggregate": report.aggregate},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"[eval-ci] 首次运行，已写入 baseline → {baseline_path}")
            return 0
        print(
            f"[eval-ci] WARN baseline 缺失 ({baseline_path})；"
            "首次接入 CI 时用 --update-baseline 写一份，本次不阻断"
        )
        return 2

    violations = _check_regression(
        current_agg=report.aggregate,
        baseline_agg=baseline.get("aggregate", {}),
        threshold=threshold,
    )
    if violations:
        print("[eval-ci] REGRESSION 检测到以下退化：")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("[eval-ci] PASS 所有受守护指标均未退化")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.evals.ci_gate")
    parser.add_argument("--dataset", default="all")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help=f"baseline 报告 JSON 路径（默认 {DEFAULT_BASELINE_PATH}）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="退化阈值（0-1，默认 0.05 即 5%%）",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="把当次结果写入 baseline（仅在 baseline 不存在或显式想刷新时使用）",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run(
            dataset=args.dataset,
            baseline_path=args.baseline,
            threshold=args.threshold,
            update_baseline=args.update_baseline,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
