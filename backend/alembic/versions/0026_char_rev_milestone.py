"""character_revisions: milestone_chapter_index (Sprint 17-A防漂移).

Revision ID: 0026_char_rev_milestone
Revises: 0025_plot_thread_eta
Create Date: 2026-05-28

加 milestone_chapter_index（Integer NULL + index）：每 50 章把该角色流水
revisions 浓缩成 1 条 snapshot 行（field='_milestone'）。ContextBuilder
优先读最近 milestone 作为基线，再叠加之后的少量流水。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_char_rev_milestone"
down_revision: str | None = "0025_plot_thread_eta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "character_revisions",
        sa.Column("milestone_chapter_index", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_character_revisions_milestone",
        "character_revisions",
        ["milestone_chapter_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_character_revisions_milestone", "character_revisions")
    op.drop_column("character_revisions", "milestone_chapter_index")
