"""风格样本 ORM。

用户可以为项目上传若干段"风格示例"片段（如：心仪作家的开头段落、
自己之前的成功小说片段）。ContextBuilder 在写场景时，会按当前场景
的目标/冲突召回 top-K 段相似度最高的样本，作为风格指引插入到 prompt。

为兼容 SQLite 测试与未来真正接入 pgvector，embedding 列用一个轻量
TypeDecorator：PG 上落 JSON 字符串 / SQLite 上落 JSON 文本，业务层
读写都按 list[float] 处理。真正切到 pgvector 时只需替换 TypeDecorator
的实现，schema 与 ORM 接口保持稳定（Sprint 14-C4 KISS：先打通链路）。
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class EmbeddingType(TypeDecorator):
    """跨方言的 embedding 列。

    存储 list[float]；底层根据方言落地到 JSON / JSONB。需要替换为
    pgvector 时，把这里的 impl 改为 `pgvector.sqlalchemy.Vector(1536)`
    并在 process_bind_param/process_result_value 透传即可。
    """

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, str):
            # 允许传入已序列化的 JSON 字符串
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return parsed
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value


class StyleSample(Base, TenantMixin, TimestampMixin):
    __tablename__ = "style_samples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[Optional[list[float]]] = mapped_column(EmbeddingType, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
