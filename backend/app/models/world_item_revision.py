"""WorldItemRevision ORM.

Sprint 12-C：世界观条目版本链。镜像 character_revision 的字段结构，
让 world_item（地点 / 势力 / 硬规则）拥有完整的演进时间线 + AI 推演审核流程。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class WorldItemRevision(Base, TenantMixin, TimestampMixin):
    __tablename__ = "world_item_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("world_items.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    # 'user_edit' | 'copilot' | 'ai_inferred'
    source: Mapped[str] = mapped_column(String(32), default="user_edit")
    scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 'applied' | 'pending' | 'rejected' | 'superseded'
    status: Mapped[str] = mapped_column(String(32), default="applied")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
