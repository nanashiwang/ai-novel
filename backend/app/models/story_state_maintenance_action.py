from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class StoryStateMaintenanceAction(Base, TenantMixin, TimestampMixin):
    __tablename__ = "story_state_maintenance_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("chapters.id"),
        nullable=True,
        index=True,
    )
    scene_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("scenes.id"),
        nullable=True,
        index=True,
    )
    draft_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("draft_versions.id"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    target_state_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("story_state_items.id"),
        nullable=True,
        index=True,
    )
    source_state_ids: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=list,
        server_default=text("'[]'"),
    )
    target_requirement_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("chapter_state_requirements.id"),
        nullable=True,
        index=True,
    )
    risk_level: Mapped[str] = mapped_column(String(16), default="low", server_default="low")
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(32),
        default="suggested",
        server_default="suggested",
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    patch_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        server_default=text("'{}'"),
    )
    before_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        server_default=text("'{}'"),
    )
    after_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        server_default=text("'{}'"),
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
