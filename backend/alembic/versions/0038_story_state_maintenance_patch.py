"""store AI maintenance action patch.

Revision ID: 0038_story_state_maintenance_patch
Revises: 0037_story_state_maintenance_actions
Create Date: 2026-05-31
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038_story_state_maintenance_patch"
down_revision: str | None = "0037_story_state_maintenance_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    dict_default = sa.text("'{}'::jsonb") if is_postgres else "{}"

    if is_postgres:
        op.execute(
            "ALTER TABLE story_state_maintenance_actions "
            "ADD COLUMN IF NOT EXISTS patch_json JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
        return

    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("story_state_maintenance_actions")
    }
    if "patch_json" in existing_columns:
        return
    op.add_column(
        "story_state_maintenance_actions",
        sa.Column("patch_json", json_type, nullable=False, server_default=dict_default),
    )


def downgrade() -> None:
    op.drop_column("story_state_maintenance_actions", "patch_json")
