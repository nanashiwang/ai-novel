"""Chapter: target_words + scene_beats (Sprint 16-E1).

Revision ID: 0024_chapter_budget
Revises: 0023_prompt_experiments
Create Date: 2026-05-23

把"章节字数预算"和"场景拍点"显式落库：
- target_words：novel_planner 拆 chapters 时按 spec.target_word_count /
  target_chapter_count 反推默认值，可被 outline prompt 覆盖。
- scene_beats：章内剧情拍点，供后续规则预算器合并成实际 scene。
两个字段都是 ADD COLUMN IF NOT EXISTS；旧数据 target_words=0、scene_beats=[]，
writer 路径会 fallback 到旧的 estimate_words 平摊逻辑，向后兼容。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_chapter_budget"
down_revision: str | None = "0023_prompt_experiments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.add_column(
        "chapters",
        sa.Column("target_words", sa.Integer(), nullable=False, server_default="0"),
    )
    # JSONB on PG, JSON elsewhere（SQLite tests / 兼容）
    json_type = sa.dialects.postgresql.JSONB() if dialect == "postgresql" else sa.JSON()
    op.add_column(
        "chapters",
        sa.Column(
            "scene_beats",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if dialect == "postgresql" else sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chapters", "scene_beats")
    op.drop_column("chapters", "target_words")
