"""离线评测体系（Sprint 14-C1）。

包含：
- datasets/：固定数据集（YAML），用于回归 scene 写作质量
- metrics.py：客观指标（句长、对话比、词汇多样性等）
- judges.py：LLM-as-judge（coherence/dialogue/pacing/show_dont_tell）
- runner.py：批量跑评测、聚合统计、落地 JSON 报告
- cli.py：`python -m app.evals.cli run --dataset all`

设计取向：
- KISS：纯开发者工具，**不**对外暴露 HTTP API
- YAGNI：先做 scene 级；chapter/book 级留 TODO
- 离线友好：默认走 stub judge，无需 OPENAI_API_KEY 也能跑通
"""
