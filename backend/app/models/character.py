from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class Character(Base, TenantMixin, TimestampMixin):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    role: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    secret: Mapped[str] = mapped_column(Text, default="")
    arc: Mapped[str] = mapped_column(Text, default="")
    relationships: Mapped[dict] = mapped_column(JSON, default=dict)
    current_state: Mapped[dict] = mapped_column(JSON, default=dict)
    # Sprint 17-D 角色登场约束：该角色首次以正面戏份登场的章节号。
    # 由 bible LLM 生成，作为 plan_scenes / audit 的硬约束依据，杜绝
    # plot_threads 描述里"全书人物清单"导致的角色提前空降。
    # NULL = 未指定，渲染时不强制约束（保持向后兼容）。
    first_appearance_chapter: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
