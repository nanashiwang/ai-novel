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
    scene_purpose: Mapped[str] = mapped_column(Text, default="")
    entry_state: Mapped[str] = mapped_column(Text, default="")
    exit_state: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    conflict: Mapped[str] = mapped_column(Text, default="")
    must_include: Mapped[list[str]] = mapped_column(JSON, default=list)
    must_avoid: Mapped[list[str]] = mapped_column(JSON, default=list)
    emotion_start: Mapped[str] = mapped_column(String(120), default="")
    emotion_end: Mapped[str] = mapped_column(String(120), default="")
    reveal: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="planned")
    # 持久化的场景预算。scene_beats 是章内剧情拍点，生成场景计划时会把
    # 相邻 beat 合并到实际 scene，并把本场目标字数与覆盖范围固定下来。
    target_words: Mapped[int] = mapped_column(Integer, default=0)
    beat_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    beat_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    beat_group_summary: Mapped[str] = mapped_column(Text, default="")
    budget_reason: Mapped[str] = mapped_column(Text, default="")
    # Sprint 14-C6：Per-scene POV 锚定。空 = 无固定 POV（沿用 spec.narrative_pov），
    # 非空 = 该场景视角主角名（必须出现在 characters 中）。ContextBuilder 据此
    # 隐藏其它角色的 secret/motivation/arc/current_state，避免"全知视角泄密"。
    pov_character_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Sprint 17-B 全局时间线：每场结构化时间戳，让长程章节生成能感知
    # "现在距开篇过了多久"，避免季节/年龄/事件时序矛盾。
    # in_story_day_offset：从开篇第 0 天起的偏移（开篇当日 = 0）
    # time_of_day：morning / noon / afternoon / evening / night / dawn / dusk
    # duration_minutes：本场在故事时间内持续的分钟数
    in_story_day_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_of_day: Mapped[str] = mapped_column(String(16), default="")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
