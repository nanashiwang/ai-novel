from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.embedding_type import EmbeddingType

from .common import TenantMixin, TimestampMixin


class MemoryEntry(Base, TenantMixin, TimestampMixin):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="scene")
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    memory_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=3)
    # Sprint 13-B1：语义向量列，PG 上走 pgvector(1536)，其它方言回落 JSON
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType(), nullable=True)
    # Sprint 14-C2：分层摘要记忆。
    # level: L1 = scene 摘要（原始）、L2 = 章摘要、L3 = 卷摘要、L4 = 整书摘要。
    # arc_window: 该摘要覆盖的剧情范围描述，例如 'ch1-ch3' 或 'book'。
    level: Mapped[str] = mapped_column(String(8), default="L1", server_default="L1")
    arc_window: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
