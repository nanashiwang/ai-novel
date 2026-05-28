"""characters: first_appearance_chapter (Sprint 17-D 角色登场约束).

Revision ID: 0031_character_first_appearance
Revises: 0030_merge_memory_and_story_state_heads
Create Date: 2026-05-28

加 first_appearance_chapter（Integer NULL + index）：bible LLM 估计该角色
首次以正面戏份登场的章节号。用于 plan_scenes 阶段限制"未来角色被写进
早期章节"，以及 audit 反向校验"本章新出现角色是否到了登场时机"。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_character_first_appearance"
down_revision: str | None = "0030_merge_memory_and_story_state_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("first_appearance_chapter", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_characters_first_appearance",
        "characters",
        ["first_appearance_chapter"],
    )


def downgrade() -> None:
    op.drop_index("ix_characters_first_appearance", "characters")
    op.drop_column("characters", "first_appearance_chapter")
