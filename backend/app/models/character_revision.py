from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class CharacterRevision(Base, TenantMixin, TimestampMixin):
    """人物字段版本链。

    所有人物字段修改（手动 / Copilot 提案 / AI 自动推演）统一落到这张表。
    consumer：
    - ContextBuilder 永远只读 status='applied' 的最新 revision 作为权威字段值
    - 历史版本回滚 = 把目标 revision 重新 apply
    - AI 推演产出 status='pending'，需要用户审核

    与 revisions（设定共创）的关系：设定共创对话产生的 character 修改也
    落到这里，source='copilot'；本表是 character 字段变更的"唯一真相源"。
    """

    __tablename__ = "character_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )

    # 受 CHARACTER_FIELDS 白名单约束，由 service 层校验
    field: Mapped[str] = mapped_column(String(64))
    # 新旧值都用 JSON 存，避免 str/dict/list 字段类型分裂
    old_value: Mapped[Any] = mapped_column(JSON, default=None, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, default=None, nullable=True)
    # AI 推演时必填 evidence 原文片段；用户编辑/Copilot 可空
    reason: Mapped[str] = mapped_column(Text, default="")
    # 'user_edit' | 'copilot' | 'ai_inferred'
    source: Mapped[str] = mapped_column(String(16))
    # ai_inferred 触发该 revision 的场景，便于时间线展示
    scene_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("scenes.id"))
    # 'pending' | 'applied' | 'rejected' | 'superseded'
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    applied_by: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"))
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Sprint 17-A 防漂移：里程碑快照。每 50 章把流水 revisions 浓缩成 1 条
    # snapshot 写回，ContextBuilder._fmt_character_actions 优先读最近的
    # milestone 作为基线，再叠加 milestone 之后的少量流水。
    # 普通 revision 此字段为 NULL；snapshot 行 field='_milestone'、
    # new_value 是结构化人物状态字典。
    milestone_chapter_index: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )
