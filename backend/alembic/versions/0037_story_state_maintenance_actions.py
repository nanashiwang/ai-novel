"""story state AI maintenance action log.

Revision ID: 0037_story_state_maintenance_actions
Revises: 0036_story_state_item_lifecycle
Create Date: 2026-05-31
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0037_story_state_maintenance_actions"
down_revision: str | None = "0036_story_state_item_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    list_default = sa.text("'[]'::jsonb") if is_postgres else "[]"
    dict_default = sa.text("'{}'::jsonb") if is_postgres else "{}"

    op.create_table(
        "story_state_maintenance_actions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=True),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("draft_id", sa.String(length=64), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("target_state_id", sa.String(length=64), nullable=True),
        sa.Column("source_state_ids", json_type, nullable=False, server_default=list_default),
        sa.Column("target_requirement_id", sa.String(length=64), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="suggested"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("before_json", json_type, nullable=False, server_default=dict_default),
        sa.Column("after_json", json_type, nullable=False, server_default=dict_default),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["draft_versions.id"]),
        sa.ForeignKeyConstraint(["target_state_id"], ["story_state_items.id"]),
        sa.ForeignKeyConstraint(["target_requirement_id"], ["chapter_state_requirements.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_story_state_maintenance_actions_org_project",
        "story_state_maintenance_actions",
        ["organization_id", "project_id"],
    )
    op.create_index(
        "ix_story_state_maintenance_actions_project_created",
        "story_state_maintenance_actions",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_story_state_maintenance_actions_project_status",
        "story_state_maintenance_actions",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_story_state_maintenance_actions_draft",
        "story_state_maintenance_actions",
        ["draft_id"],
    )
    op.create_index(
        "ix_story_state_maintenance_actions_target_state",
        "story_state_maintenance_actions",
        ["target_state_id"],
    )
    op.create_index(
        "ix_story_state_maintenance_actions_target_requirement",
        "story_state_maintenance_actions",
        ["target_requirement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_story_state_maintenance_actions_target_requirement",
        table_name="story_state_maintenance_actions",
    )
    op.drop_index(
        "ix_story_state_maintenance_actions_target_state",
        table_name="story_state_maintenance_actions",
    )
    op.drop_index(
        "ix_story_state_maintenance_actions_draft",
        table_name="story_state_maintenance_actions",
    )
    op.drop_index(
        "ix_story_state_maintenance_actions_project_status",
        table_name="story_state_maintenance_actions",
    )
    op.drop_index(
        "ix_story_state_maintenance_actions_project_created",
        table_name="story_state_maintenance_actions",
    )
    op.drop_index(
        "ix_story_state_maintenance_actions_org_project",
        table_name="story_state_maintenance_actions",
    )
    op.drop_table("story_state_maintenance_actions")
