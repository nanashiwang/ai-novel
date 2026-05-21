"""信息释放 ledger（Sprint 14-C5）。

把"主角真实身份是 X / 凶手是 Y / 神器的真名"等需要分阶段释放的事实集中
登记，配合 LedgerService 在 write_scene 之后做"信息泄露"校验：

- ``owners``：谁本就知道这个事实（角色 id / 世界条目 id）。
- ``disclosed_to``：哪些角色已经被告知（即"读者已经在场看见"）。
- ``status``：secret / partial / public 三态，partial 表示"暗示性透露"。
- ``first_revealed_scene_id`` / ``planned_reveal_chapter``：留存揭示节奏的
  审计快照，便于后期分析作者节奏 vs AI 推演节奏的偏差。

KISS：v1 仅做关键词命中校验，因此本表不强约束 owners/disclosed_to 必须
存在；外键留给 character/world_item 字符串引用，删除该角色后此处变成
悬空 id 也只是降低召回精度，不影响主流程。
"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class InformationLedger(Base, TenantMixin, TimestampMixin):
    __tablename__ = "information_ledger"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    owners: Mapped[list[str]] = mapped_column(JSON, default=list)
    disclosed_to: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_revealed_scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    planned_reveal_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="secret", nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
