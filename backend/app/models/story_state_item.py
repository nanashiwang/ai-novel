from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class StoryStateItem(Base, TenantMixin, TimestampMixin):
    __tablename__ = "story_state_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    state_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    superseded_by_state_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("story_state_items.id"),
        nullable=True,
        index=True,
    )
    status_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    value_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        server_default=text("'{}'"),
    )
    source_chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    updated_in_chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_hard_constraint: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
    )
