from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class Volume(Base, TenantMixin, TimestampMixin):
    __tablename__ = "volumes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    volume_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="planned")


class Chapter(Base, TenantMixin, TimestampMixin):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    volume_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("volumes.id"))
    chapter_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    conflict: Mapped[str] = mapped_column(Text, default="")
    ending_hook: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="planned")
    # Sprint 16-E1：章节级字数预算与场景拍点。
    # target_words: 该章目标字数；novel_planner 会按 spec.target_word_count /
    # target_chapter_count 反推默认值，可被 outline prompt 覆盖。
    # 0 = 未设置，writer 路径需 fallback 到旧的 estimate_words 平摊逻辑。
    target_words: Mapped[int] = mapped_column(Integer, default=0)
    # scene_beats: 章内每场的功能/动作要点（list[str]），由 novel_planner 在
    # 生成 chapters 时一并产出；scene_count 由 len(scene_beats) 决定，无 beat
    # 时回落到调用方指定的 scenes_per_chapter。
    scene_beats: Mapped[list[str]] = mapped_column(JSON, default=list)
