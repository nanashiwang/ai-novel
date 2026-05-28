"""关键状态防遗忘：状态项 / 历史 / 章节承接表 (Sprint 18-A1).

Revision ID: 0029_story_state_tables
Revises: 0028_chapters_pacing
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029_story_state_tables"
down_revision: str | None = "0028_chapters_pacing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "story_state_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("state_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "value_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_chapter_id", sa.String(length=64), nullable=True),
        sa.Column("source_scene_id", sa.String(length=64), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_in_chapter_id", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_hard_constraint", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_story_state_items_org_project",
        "story_state_items",
        ["organization_id", "project_id"],
    )
    op.create_index(
        "ix_story_state_items_project_state_type",
        "story_state_items",
        ["project_id", "state_type"],
    )
    op.create_index(
        "ix_story_state_items_project_status",
        "story_state_items",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_story_state_items_project_priority",
        "story_state_items",
        ["project_id", "priority", "updated_at"],
    )

    op.create_table(
        "story_state_history",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("state_item_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=True),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column(
            "before_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "after_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["state_item_id"], ["story_state_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_story_state_history_project_state_item",
        "story_state_history",
        ["project_id", "state_item_id", "created_at"],
    )
    op.create_index(
        "ix_story_state_history_project_chapter",
        "story_state_history",
        ["project_id", "chapter_id", "created_at"],
    )

    op.create_table(
        "chapter_state_requirements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("state_item_id", sa.String(length=64), nullable=False),
        sa.Column("requirement_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.ForeignKeyConstraint(["state_item_id"], ["story_state_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chapter_state_requirements_project_chapter",
        "chapter_state_requirements",
        ["project_id", "chapter_id", "priority"],
    )
    op.create_index(
        "ix_chapter_state_requirements_project_state_item",
        "chapter_state_requirements",
        ["project_id", "state_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chapter_state_requirements_project_state_item",
        table_name="chapter_state_requirements",
    )
    op.drop_index(
        "ix_chapter_state_requirements_project_chapter",
        table_name="chapter_state_requirements",
    )
    op.drop_table("chapter_state_requirements")

    op.drop_index(
        "ix_story_state_history_project_chapter",
        table_name="story_state_history",
    )
    op.drop_index(
        "ix_story_state_history_project_state_item",
        table_name="story_state_history",
    )
    op.drop_table("story_state_history")

    op.drop_index("ix_story_state_items_project_priority", table_name="story_state_items")
    op.drop_index("ix_story_state_items_project_status", table_name="story_state_items")
    op.drop_index("ix_story_state_items_project_state_type", table_name="story_state_items")
    op.drop_index("ix_story_state_items_org_project", table_name="story_state_items")
    op.drop_table("story_state_items")
