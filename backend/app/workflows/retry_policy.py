"""Workflow 共享重试策略。

把 RetryPolicy 集中在此文件，避免在每个 workflow 重复定义：
- _MODEL_ACTIVITY_RETRY：模型密集型 activity（生成圣经/大纲/场景/正文）。
  最多 3 次尝试，避免临时 429/5xx 反复烧 token；后续可拆 provider 级策略。
- _STATUS_ACTIVITY_RETRY：状态机活动（mark_job_status 等）。
  纯数据库写入，故障多为短暂网络抖动，可以更激进地重试。
"""
from __future__ import annotations

from datetime import timedelta

from temporalio.common import RetryPolicy

MODEL_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

STATUS_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)
