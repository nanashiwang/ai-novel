from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class PlotThread(Base, TenantMixin, TimestampMixin):
    __tablename__ = "plot_threads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    thread_type: Mapped[str] = mapped_column(String(64), default="main")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="open")
    related_characters: Mapped[list[str]] = mapped_column(JSON, default=list)
    opened_at_scene_id: Mapped[Optional[str]] = mapped_column(String(64))
    closed_at_scene_id: Mapped[Optional[str]] = mapped_column(String(64))
    # Sprint 17-A：开线时估计的预期收线章节；ContextBuilder 读时若已超期则
    # 把线索标 [stalled]，强制下一章必须推进或显式宣告冻结/废弃。
    expected_resolve_chapter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

