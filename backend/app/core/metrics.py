"""平台核心指标定义。

按优化方向文档 §4.4 选最有运营价值的 5 个指标。结构：
- jobs_created_total — 按 job_type / status 拆分；统计任务量与失败率
- quota_consumed_words_total — 按 quota_key 拆分；账单核对的基础
- model_call_latency_ms — Histogram；模型 API 延迟分布
- exports_created_total — 按 export_type 拆分
- api_request_duration_ms — Histogram；FastAPI middleware 自动埋点

`/metrics` endpoint 仅限 platform admin 访问（避免公网暴露内部指标）。
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Counters --------------------------------------------------------------

JOBS_CREATED = Counter(
    "novelflow_jobs_created_total",
    "Number of generation_jobs created, by job_type and current status",
    ["job_type", "status"],
)

QUOTA_CONSUMED = Counter(
    "novelflow_quota_consumed_total",
    "Quota actually consumed (committed) by quota_key",
    ["quota_key"],
)

EXPORTS_CREATED = Counter(
    "novelflow_exports_created_total",
    "Export files created, by export_type",
    ["export_type"],
)

# Histograms ------------------------------------------------------------

MODEL_CALL_LATENCY = Histogram(
    "novelflow_model_call_latency_ms",
    "Latency of ModelGateway calls in milliseconds, by task_type and status",
    ["task_type", "status"],
    # 桶覆盖 50ms 到 60s 的实际 LLM 请求分布
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000),
)

API_REQUEST_DURATION = Histogram(
    "novelflow_api_request_duration_ms",
    "API request duration in milliseconds, by route and status_code",
    ["route", "method", "status_code"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)


def render_metrics() -> tuple[bytes, str]:
    """返回 (body, content_type)，供 /metrics endpoint 使用。"""
    return generate_latest(), CONTENT_TYPE_LATEST
