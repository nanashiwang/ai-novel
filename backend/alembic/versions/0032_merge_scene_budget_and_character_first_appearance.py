"""merge scene budget and character first appearance heads.

Revision ID: 0032_merge_scene_budget_and_character_first_appearance
Revises: 0031_character_first_appearance, 0031_scene_budget_fields
Create Date: 2026-05-29

This merge migration keeps the Alembic graph to a single head after the
parallel Sprint 17-D and scene budget migrations.
"""
from __future__ import annotations

from collections.abc import Sequence


revision: str = "0032_merge_scene_budget_and_character_first_appearance"
down_revision: tuple[str, str] = (
    "0031_character_first_appearance",
    "0031_scene_budget_fields",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
