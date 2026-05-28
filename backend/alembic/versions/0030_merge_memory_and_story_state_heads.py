"""merge memory recall indexes and story state tables heads.

Revision ID: 0030_merge_memory_story_state
Revises: 0012_memory_recall_indexes, 0029_story_state_tables
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence


revision: str = "0030_merge_memory_story_state"
down_revision: tuple[str, str] = (
    "0012_memory_recall_indexes",
    "0029_story_state_tables",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
