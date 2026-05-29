from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class ContinuityIssue(Base, TenantMixin, TimestampMixin):
    __tablename__ = "continuity_issues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("chapters.id"))
    scene_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("scenes.id"))
    story_state_item_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("story_state_items.id"),
        nullable=True,
        index=True,
    )
    issue_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="open")
