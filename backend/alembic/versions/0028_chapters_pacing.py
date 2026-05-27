"""chapters: pacing_type + emotion_intensity (Sprint 17-B A1).

Revision ID: 0028_chapters_pacing
Revises: 0027_scenes_temporal
Create Date: 2026-05-28

加 2 个节奏字段，让大纲阶段强制按节奏分布、写作阶段注入节奏目标、
审计阶段校验是否符合节奏：
- pacing_type (String(16) DEFAULT '')：setup/rising/climax/cool_down/transition
- emotion_intensity (Integer DEFAULT 3)：1-5
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_chapters_pacing"
down_revision: str | None = "0027_scenes_temporal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chapters",
        sa.Column("pacing_type", sa.String(length=16), nullable=False, server_default=""),
    )
    op.add_column(
        "chapters",
        sa.Column("emotion_intensity", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("chapters", "emotion_intensity")
    op.drop_column("chapters", "pacing_type")
