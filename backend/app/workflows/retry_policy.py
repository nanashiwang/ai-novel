"""Workflow 共享重试策略。

把 RetryPolicy 集中在此文件，避免在每个 workflow 重复定义：
- _MODEL_ACTIVITY_RETRY：模型密集型 activity（生成圣经/大纲/场景/正文）。
  最多 3 次尝试，避免临时 429/5xx 反复烧 token；后续可拆 provider 级策略。
- _STATUS_ACTIVITY_RETRY：状态机活动（mark_job_status 等）。
  纯数据库写入，故障多为短暂网络抖动，可以更激进地重试。

异常分级：
业务异常（AppError 子类、ValueError 等参数/语义错误）即使在 retry 也只会失败，
反复重试只会浪费 token 和 worker 时间。Temporal Python SDK 把异常的
`type(exc).__name__` 作为 ApplicationError.type 传递，所以这里枚举所有
不应重试的业务异常类名。系统异常（HTTPError、TimeoutError、连接错误等）
落在白名单之外，自动走重试路径。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio.common import RetryPolicy

# 业务/参数类异常：重试不会改变结果，直接失败让 mark_job_status 释放 quota。
# 字符串与 type(exc).__name__ 直接对比；新增业务异常子类时需要同步在此登记。
_NON_RETRYABLE_BUSINESS_ERRORS = [
    "AppError",
    "NotFoundError",
    "PermissionDenied",
    "QuotaInsufficient",
    "ValueError",
    "ValidationError",
    "TypeError",
]

MODEL_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
    non_retryable_error_types=_NON_RETRYABLE_BUSINESS_ERRORS,
)

STATUS_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
    non_retryable_error_types=_NON_RETRYABLE_BUSINESS_ERRORS,
)

