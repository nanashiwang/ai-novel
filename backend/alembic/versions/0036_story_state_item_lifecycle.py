"""story_state_items: merge and supersede metadata.

Revision ID: 0036_story_state_item_lifecycle
Revises: 0035_chapter_state_requirement_lifecycle
Create Date: 2026-05-31
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_story_state_item_lifecycle"
down_revision: str | None = "0035_chapter_state_requirement_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE story_state_items "
            "ADD COLUMN IF NOT EXISTS superseded_by_state_id VARCHAR(64)"
        )
        op.execute(
            "ALTER TABLE story_state_items "
            "ADD COLUMN IF NOT EXISTS status_reason TEXT NOT NULL DEFAULT ''"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_story_state_items_superseded_by "
            "ON story_state_items(superseded_by_state_id)"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE story_state_items "
            "ADD CONSTRAINT fk_story_state_items_superseded_by "
            "FOREIGN KEY (superseded_by_state_id) REFERENCES story_state_items(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        return

    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("story_state_items")}
    if "superseded_by_state_id" not in existing:
        op.add_column(
            "story_state_items",
            sa.Column(
                "superseded_by_state_id",
                sa.String(length=64),
                sa.ForeignKey("story_state_items.id"),
                nullable=True,
            ),
        )
    if "status_reason" not in existing:
        op.add_column(
            "story_state_items",
            sa.Column("status_reason", sa.Text(), nullable=False, server_default=""),
        )
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("story_state_items")}
    if "ix_story_state_items_superseded_by" not in existing_indexes:
        op.create_index(
            "ix_story_state_items_superseded_by",
            "story_state_items",
            ["superseded_by_state_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_story_state_items_superseded_by", table_name="story_state_items")
    op.drop_column("story_state_items", "status_reason")
    op.drop_column("story_state_items", "superseded_by_state_id")
