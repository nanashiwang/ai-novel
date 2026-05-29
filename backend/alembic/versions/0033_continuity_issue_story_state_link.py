"""continuity_issues: link issues to story state items.

Revision ID: 0033_continuity_issue_story_state_link
Revises: 0032_merge_scene_budget_and_character_first_appearance
Create Date: 2026-05-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0033_continuity_issue_story_state_link"
down_revision: str | None = "0032_merge_scene_budget_and_character_first_appearance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE continuity_issues ADD COLUMN IF NOT EXISTS "
            "story_state_item_id VARCHAR(64)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_continuity_issues_story_state_item_id "
            "ON continuity_issues(story_state_item_id)"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE continuity_issues "
            "ADD CONSTRAINT fk_continuity_issues_story_state_item_id "
            "FOREIGN KEY (story_state_item_id) REFERENCES story_state_items(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        return

    existing = {col["name"] for col in sa.inspect(bind).get_columns("continuity_issues")}
    if "story_state_item_id" not in existing:
        op.add_column(
            "continuity_issues",
            sa.Column(
                "story_state_item_id",
                sa.String(length=64),
                sa.ForeignKey("story_state_items.id"),
                nullable=True,
            ),
        )
    op.create_index(
        "ix_continuity_issues_story_state_item_id",
        "continuity_issues",
        ["story_state_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_continuity_issues_story_state_item_id", table_name="continuity_issues")
    op.drop_column("continuity_issues", "story_state_item_id")
