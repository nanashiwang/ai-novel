"""为 model_calls 增加 metadata JSON 字段

Revision ID: 0018_model_calls_metadata
Revises: 0017_memory_levels
Create Date: 2026-05-22

Sprint 14-C3：多 agent 场景写作把单步生成拆成 planner → drafter → stylist
三步，每步都会落一条 model_calls 记录。metadata 字段用来记录 pipeline_step
等结构化诊断信息，便于运维与回溯。

兼容性：旧数据 metadata 默认 NULL，老代码不读取该字段即可正常工作。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_model_calls_metadata"
down_revision: str | None = "0017_memory_levels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_calls",
        sa.Column("metadata", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_calls", "metadata")
