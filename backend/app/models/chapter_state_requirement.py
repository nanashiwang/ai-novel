from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class ChapterStateRequirement(Base, TenantMixin, TimestampMixin):
    __tablename__ = "chapter_state_requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(String(64), ForeignKey("chapters.id"), index=True)
    state_item_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("story_state_items.id"),
        index=True,
    )
    requirement_type: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
