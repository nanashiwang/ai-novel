"""Memory embedding column + HNSW index

Revision ID: 0016_memory_embedding_hnsw
Revises: 0015_world_plot_revisions
Create Date: 2026-05-20 22:30:00

Sprint 13-B1：为 memory_entries 加 pgvector 嵌入列与 HNSW 索引。

- 启用 vector 扩展（生产环境镜像已带 pgvector/pgvector:pg16）
- 嵌入维度 1536（与 text-embedding-3-small 对齐；切换 provider 时如需
  改维，必须新建迁移并重建索引，下游召回链路同步更新）
- HNSW 参数：m=16, ef_construction=64 —— 通用平衡档；后续按召回评测调参
- 索引仅覆盖 embedding IS NOT NULL 的行，老数据不强制回填
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_memory_embedding_hnsw"
down_revision: str | None = "0015_world_plot_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect != "postgresql":
        # SQLite / 其它方言无需 pgvector；ORM 已用 EmbeddingType 回落 JSON
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE memory_entries "
        "ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )
    # WHERE 子句只把已填向量的行纳入索引，节省空间且避免对 NULL 排序
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memory_embedding_hnsw "
        "ON memory_entries USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_memory_embedding_hnsw")
    op.execute("ALTER TABLE memory_entries DROP COLUMN IF EXISTS embedding")
    # 不主动 DROP EXTENSION vector：可能被其它表/索引依赖
