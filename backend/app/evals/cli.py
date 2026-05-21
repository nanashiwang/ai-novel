"""离线评测 CLI。

用法：
  python -m app.evals.cli run --dataset all --judge-disabled
  python -m app.evals.cli run --dataset xuanhuan_01

参数：
  --dataset       要跑的数据集 id 或 "all"（默认 all）
  --judge-disabled 跳过 LLM judge（默认开启；CI 必须用此模式）
  --output-dir    覆盖默认报告目录
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.evals.runner import REPORT_ROOT, run_eval_sync


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.evals.cli", description="NovelFlow 离线评测")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="运行评测")
    run_p.add_argument("--dataset", default="all", help='数据集 id 或 "all"')
    # 用 store_true 默认 False，但任务要求"默认 stub"，所以 CLI 文档约定使用方
    # 自行加 --judge-disabled；这里同时支持 --judge-enabled 反向打开 LLM。
    run_p.add_argument(
        "--judge-disabled",
        action="store_true",
        default=False,
        help="跳过 LLM judge（CI 推荐）",
    )
    run_p.add_argument(
        "--judge-enabled",
        action="store_true",
        default=False,
        help="启用 LLM judge（需配置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY）",
    )
    run_p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"报告输出目录（默认 {REPORT_ROOT}）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd != "run":
        parser.print_help()
        return 2

    # 默认行为：disabled。如显式 --judge-enabled 则启用真实 LLM。
    judge_disabled = True
    if args.judge_enabled and not args.judge_disabled:
        judge_disabled = False

    report = run_eval_sync(
        dataset=args.dataset,
        judge_disabled=judge_disabled,
        output_dir=args.output_dir,
    )
    # 打印简短摘要到 stdout，便于在 CI 日志里直接读
    print(f"[eval] samples={report.dataset_count} judge_disabled={report.judge_disabled}")
    for sample in report.samples:
        print(
            f"  - {sample.sample_id} ({sample.genre}) "
            f"dialog={sample.objective_metrics.get('dialogue_ratio')} "
            f"lex_div={sample.objective_metrics.get('lexical_diversity')} "
            f"judge_avg={sample.judge_aggregate}"
        )
    print(f"[eval] aggregate={report.aggregate}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
