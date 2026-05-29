"""chapter_state_requirements: source metadata.

Revision ID: 0034_chapter_state_requirement_source
Revises: 0033_continuity_issue_story_state_link
Create Date: 2026-05-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0034_chapter_state_requirement_source"
down_revision: str | None = "0033_continuity_issue_story_state_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS source_chapter_id VARCHAR(64)"
        )
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS source_scene_id VARCHAR(64)"
        )
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS target_chapter_id VARCHAR(64)"
        )
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS origin_type VARCHAR(32) "
            "NOT NULL DEFAULT 'current_chapter_extract'"
        )
        op.execute(
            "UPDATE chapter_state_requirements "
            "SET target_chapter_id = chapter_id "
            "WHERE target_chapter_id IS NULL"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chapter_state_requirements_project_origin "
            "ON chapter_state_requirements(project_id, origin_type)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chapter_state_requirements_project_source_chapter "
            "ON chapter_state_requirements(project_id, source_chapter_id)"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE chapter_state_requirements "
            "ADD CONSTRAINT fk_chapter_state_requirements_source_chapter "
            "FOREIGN KEY (source_chapter_id) REFERENCES chapters(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE chapter_state_requirements "
            "ADD CONSTRAINT fk_chapter_state_requirements_source_scene "
            "FOREIGN KEY (source_scene_id) REFERENCES scenes(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE chapter_state_requirements "
            "ADD CONSTRAINT fk_chapter_state_requirements_target_chapter "
            "FOREIGN KEY (target_chapter_id) REFERENCES chapters(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        return

    existing = {
        col["name"]
        for col in sa.inspect(bind).get_columns("chapter_state_requirements")
    }
    if "source_chapter_id" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column("source_chapter_id", sa.String(length=64), nullable=True),
        )
    if "source_scene_id" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column("source_scene_id", sa.String(length=64), nullable=True),
        )
    if "target_chapter_id" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column("target_chapter_id", sa.String(length=64), nullable=True),
        )
    if "origin_type" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column(
                "origin_type",
                sa.String(length=32),
                nullable=False,
                server_default="current_chapter_extract",
            ),
        )
    op.execute(
        "UPDATE chapter_state_requirements "
        "SET target_chapter_id = chapter_id "
        "WHERE target_chapter_id IS NULL"
    )
    op.create_index(
        "ix_chapter_state_requirements_project_origin",
        "chapter_state_requirements",
        ["project_id", "origin_type"],
        unique=False,
    )
    op.create_index(
        "ix_chapter_state_requirements_project_source_chapter",
        "chapter_state_requirements",
        ["project_id", "source_chapter_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chapter_state_requirements_project_source_chapter",
        table_name="chapter_state_requirements",
    )
    op.drop_index(
        "ix_chapter_state_requirements_project_origin",
        table_name="chapter_state_requirements",
    )
    op.drop_column("chapter_state_requirements", "origin_type")
    op.drop_column("chapter_state_requirements", "target_chapter_id")
    op.drop_column("chapter_state_requirements", "source_scene_id")
    op.drop_column("chapter_state_requirements", "source_chapter_id")
