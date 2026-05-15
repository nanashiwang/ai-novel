from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class DraftVersion(Base, TenantMixin, TimestampMixin):
    __tablename__ = "draft_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("chapters.id"))
    scene_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("scenes.id"))
    version_type: Mapped[str] = mapped_column(String(64), default="draft")
    content: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(64), default="draft")
    parent_version_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
