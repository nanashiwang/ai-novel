"""PromptExperiment ORM (Sprint 15-D1).

Prompt A/B 实验登记表：每行描述一次"对某个 prompt_key 做 A/B 分流"的实验。
PromptRouter 在 ModelGateway 入口处按 organization_id + project_id 哈希
稳定分流，落地的 prompt_version 与 experiment_id / variant 会被记到
model_calls.metadata_json，供评测 runner 后续按 variant 聚合对比。

简化策略（KISS / YAGNI v1）：
- 只支持二元 A/B（variant_a vs variant_b）。多臂等更复杂的场景留到 v2
- 仅按 (organization_id, project_id) 哈希分流；不支持基于用户/quota_key 的分流
- 缓存逻辑放 PromptRouter，本模型只是事实表
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class PromptExperiment(Base, TenantMixin, TimestampMixin):
    __tablename__ = "prompt_experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 实验目标 prompt：与 prompt_manager.load 的 key 一致，如 "writing/write_scene"
    prompt_key: Mapped[str] = mapped_column(String(160), index=True)
    # A/B 两个候选版本号；prompt_manager 会按 *.v{N}.md 加载
    variant_a_version: Mapped[str] = mapped_column(String(32), default="v1")
    variant_b_version: Mapped[str] = mapped_column(String(32), default="v2")
    # variant_a 的流量占比；剩余流量给 variant_b。范围 0-100
    traffic_split_pct: Mapped[int] = mapped_column(Integer, default=50)
    # 'draft' | 'active' | 'paused' | 'ended'
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
