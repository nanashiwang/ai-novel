from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class Scene(Base, TenantMixin, TimestampMixin):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(String(64), ForeignKey("chapters.id"), index=True)
    scene_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    time_marker: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    characters: Mapped[list[str]] = mapped_column(JSON, default=list)
    goal: Mapped[str] = mapped_column(Text, default="")
    conflict: Mapped[str] = mapped_column(Text, default="")
    emotion_start: Mapped[str] = mapped_column(String(120), default="")
    emotion_end: Mapped[str] = mapped_column(String(120), default="")
    reveal: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="planned")
