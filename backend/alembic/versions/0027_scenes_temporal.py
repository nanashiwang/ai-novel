"""scenes: 全局时间线字段 (Sprint 17-B B1).

Revision ID: 0027_scenes_temporal
Revises: 0026_char_rev_milestone
Create Date: 2026-05-28

加 3 个结构化时间字段，让长程章节生成能感知"现在距开篇过了多久"：
- in_story_day_offset (Integer NULL)：从开篇第 0 天起的偏移
- time_of_day (String(16) DEFAULT '')：morning / noon / afternoon / evening / night / dawn / dusk
- duration_minutes (Integer NULL)：本场持续时长

time_marker（自由文本）保留兼容，新字段做结构化补充而非替换。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_scenes_temporal"
down_revision: str | None = "0026_char_rev_milestone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scenes",
        sa.Column("in_story_day_offset", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scenes",
        sa.Column("time_of_day", sa.String(length=16), nullable=False, server_default=""),
    )
    op.add_column(
        "scenes",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_scenes_day_offset",
        "scenes",
        ["project_id", "in_story_day_offset"],
    )


def downgrade() -> None:
    op.drop_index("ix_scenes_day_offset", "scenes")
    op.drop_column("scenes", "duration_minutes")
    op.drop_column("scenes", "time_of_day")
    op.drop_column("scenes", "in_story_day_offset")
