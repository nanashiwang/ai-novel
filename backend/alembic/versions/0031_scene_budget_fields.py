"""scenes: persist scene budget assignments.

Revision ID: 0031_scene_budget_fields
Revises: 0030_merge_memory_story_state
Create Date: 2026-05-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0031_scene_budget_fields"
down_revision: str | None = "0030_merge_memory_story_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS "
            "target_words INTEGER NOT NULL DEFAULT 0"
        )
        op.execute("ALTER TABLE scenes ADD COLUMN IF NOT EXISTS beat_start INTEGER")
        op.execute("ALTER TABLE scenes ADD COLUMN IF NOT EXISTS beat_end INTEGER")
        op.execute(
            "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS "
            "beat_group_summary TEXT NOT NULL DEFAULT ''"
        )
        op.execute(
            "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS "
            "budget_reason TEXT NOT NULL DEFAULT ''"
        )
        return

    existing = {col["name"] for col in sa.inspect(bind).get_columns("scenes")}
    if "target_words" not in existing:
        op.add_column(
            "scenes",
            sa.Column("target_words", sa.Integer(), nullable=False, server_default="0"),
        )
    if "beat_start" not in existing:
        op.add_column("scenes", sa.Column("beat_start", sa.Integer(), nullable=True))
    if "beat_end" not in existing:
        op.add_column("scenes", sa.Column("beat_end", sa.Integer(), nullable=True))
    if "beat_group_summary" not in existing:
        op.add_column(
            "scenes",
            sa.Column("beat_group_summary", sa.Text(), nullable=False, server_default=""),
        )
    if "budget_reason" not in existing:
        op.add_column(
            "scenes",
            sa.Column("budget_reason", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    op.drop_column("scenes", "budget_reason")
    op.drop_column("scenes", "beat_group_summary")
    op.drop_column("scenes", "beat_end")
    op.drop_column("scenes", "beat_start")
    op.drop_column("scenes", "target_words")
