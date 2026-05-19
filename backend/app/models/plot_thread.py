from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, ForeignKey, String, Text
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

