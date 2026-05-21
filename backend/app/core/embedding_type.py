"""嵌入向量类型与配置（Sprint 13-B1）。

提供 SQLAlchemy `EmbeddingType` 与配置常量。PostgreSQL 下走 pgvector
`vector(N)` 列；非 PG 数据库（如测试用的 SQLite）回落为 JSON，确保单测仍可
跑且 ORM 行为一致——但向量相似度查询只在 PG 上有效，调用方需要明确判定。
"""
from __future__ import annotations

from sqlalchemy import JSON, types

# 维度与默认 provider 选择保持与 settings 一致；为避免 import 环依赖，
# 这里硬编码默认值，运行时由 settings 决定实际 provider 行为。
DEFAULT_EMBEDDING_DIM = 1536


try:  # pgvector-python 只在 PG 环境下有效
    from pgvector.sqlalchemy import Vector as _PgVector
except Exception:  # noqa: BLE001
    _PgVector = None  # type: ignore[assignment]


class EmbeddingType(types.TypeDecorator):
    """向量列：PG 上落 vector(dim)，其余回落 JSON。

    impl=JSON 保证 SQLite 等可以建表；PG 实际类型在 load_dialect_impl 中切换。
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):  # noqa: ANN001
        if dialect.name == "postgresql" and _PgVector is not None:
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        # 直接传 list[float]；pgvector adapter 自行处理 PG 协议
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001
        return value
