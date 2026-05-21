"""Memory recall query indexes

Revision ID: 0012_memory_recall_indexes
Revises: 0011_database_indexes
Create Date: 2026-05-21 12:20:00

为 Memory Engine 的角色/时间召回补索引。真正的 pgvector embedding/HNSW
索引仍等 embedding 字段和向量 provider 接入后单独迁移。
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_memory_recall_indexes"
down_revision: str | None = "0011_database_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_memory_project_type_created",
        "memory_entries",
        ["project_id", "memory_type", "created_at"],
    )
    op.create_index(
        "ix_memory_project_source_created",
        "memory_entries",
        ["project_id", "source_type", "source_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_project_source_created", table_name="memory_entries")
    op.drop_index("ix_memory_project_type_created", table_name="memory_entries")
