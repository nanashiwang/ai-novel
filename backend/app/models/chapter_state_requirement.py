from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class ChapterStateRequirement(Base, TenantMixin, TimestampMixin):
    __tablename__ = "chapter_state_requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(String(64), ForeignKey("chapters.id"), index=True)
    source_chapter_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("chapters.id"),
        nullable=True,
        index=True,
    )
    source_scene_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("scenes.id"),
        nullable=True,
    )
    target_chapter_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("chapters.id"),
        nullable=True,
        index=True,
    )
    origin_type: Mapped[str] = mapped_column(
        String(32),
        default="current_chapter_extract",
        server_default=text("'current_chapter_extract'"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default=text("'active'"),
        index=True,
    )
    superseded_by_requirement_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("chapter_state_requirements.id"),
        nullable=True,
        index=True,
    )
    source_issue_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("continuity_issues.id"),
        nullable=True,
        index=True,
    )
    status_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    state_item_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("story_state_items.id"),
        index=True,
    )
    requirement_type: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
