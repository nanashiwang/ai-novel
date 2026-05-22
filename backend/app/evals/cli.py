"""离线评测 CLI。

用法：
  # 数据集评测（基线 / prompt 升级前）
  python -m app.evals.cli run --dataset all --judge-disabled
  python -m app.evals.cli run --dataset xuanhuan_01

  # A/B 实验真实流量对比（消费 model_calls 历史）
  python -m app.evals.cli compare-experiment <experiment_id>
  python -m app.evals.cli compare-experiment <experiment_id> --output report.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.evals.runner import REPORT_ROOT, run_eval_sync


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.evals.cli", description="NovelFlow 离线评测")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="运行评测")
    run_p.add_argument("--dataset", default="all", help='数据集 id 或 "all"')
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

    cmp_p = sub.add_parser(
        "compare-experiment",
        help="按 experiment_id 消费 model_calls 历史，对比 A/B 两个 variant",
    )
    cmp_p.add_argument("experiment_id", help="prompt_experiments.id")
    cmp_p.add_argument(
        "--limit",
        type=int,
        default=500,
        help="最多消费的 model_calls 行数（防失控）",
    )
    cmp_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="对比报告 JSON 输出路径；不指定时打印到 stdout",
    )
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    judge_disabled = True
    if args.judge_enabled and not args.judge_disabled:
        judge_disabled = False
    report = run_eval_sync(
        dataset=args.dataset,
        judge_disabled=judge_disabled,
        output_dir=args.output_dir,
    )
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


def _cmd_compare_experiment(args: argparse.Namespace) -> int:
    # 延迟导入，避免无 DB 时也能 `--help`
    from app.core.database import AsyncSessionLocal  # noqa: PLC0415
    from app.evals.from_model_calls import compare_experiment  # noqa: PLC0415

    async def _run() -> dict:
        async with AsyncSessionLocal() as session:
            cmp = await compare_experiment(
                session,
                experiment_id=args.experiment_id,
                sample_limit=args.limit,
            )
            return cmp.to_dict()

    payload = asyncio.run(_run())
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload_json, encoding="utf-8")
        print(f"[eval] wrote comparison report → {args.output}")
    else:
        print(payload_json)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "compare-experiment":
        return _cmd_compare_experiment(args)
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
