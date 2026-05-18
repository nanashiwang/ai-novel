from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class Project(Base, TenantMixin, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200), index=True)
    genre: Mapped[str] = mapped_column(String(120), default="")
    target_word_count: Mapped[int] = mapped_column(Integer, default=0)
    target_chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    current_word_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN")
    style: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(64), default="created")
    cover_url: Mapped[str] = mapped_column(String(500), default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_reader: Mapped[str] = mapped_column(String(500), default="")


class NovelSpec(Base, TenantMixin, TimestampMixin):
    __tablename__ = "novel_specs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    premise: Mapped[str] = mapped_column(Text, default="")
    theme: Mapped[str] = mapped_column(String(500), default="")
    genre: Mapped[str] = mapped_column(String(120), default="")
    tone: Mapped[str] = mapped_column(String(500), default="")
    target_reader: Mapped[str] = mapped_column(String(500), default="")
    narrative_pov: Mapped[str] = mapped_column(String(200), default="")
    style_guide: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list)
