"""Memory entries: 分层摘要 (L1-L4) 字段

Revision ID: 0017_memory_levels
Revises: 0016_memory_embedding_hnsw
Create Date: 2026-05-22

Sprint 14-C2：分层摘要记忆。
- level: L1 scene 原文摘要；L2 章摘要；L3 卷摘要；L4 整书摘要。
- arc_window: 该摘要覆盖的章节/卷范围描述，如 'ch1-ch3'、'volume_intro'、'book'。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_memory_levels"
down_revision: str | None = "0016_memory_embedding_hnsw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_entries",
        sa.Column(
            "level",
            sa.String(length=8),
            nullable=False,
            server_default="L1",
        ),
    )
    op.add_column(
        "memory_entries",
        sa.Column("arc_window", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_memory_project_level_created",
        "memory_entries",
        ["project_id", "level", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_project_level_created", table_name="memory_entries")
    op.drop_column("memory_entries", "arc_window")
    op.drop_column("memory_entries", "level")
