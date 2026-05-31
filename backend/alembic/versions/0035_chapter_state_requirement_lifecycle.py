"""chapter_state_requirements: lifecycle fields.

Revision ID: 0035_chapter_state_requirement_lifecycle
Revises: 0034_chapter_state_requirement_source
Create Date: 2026-05-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_chapter_state_requirement_lifecycle"
down_revision: str | None = "0034_chapter_state_requirement_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active'"
        )
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS superseded_by_requirement_id VARCHAR(64)"
        )
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS source_issue_id VARCHAR(64)"
        )
        op.execute(
            "ALTER TABLE chapter_state_requirements "
            "ADD COLUMN IF NOT EXISTS status_reason TEXT NOT NULL DEFAULT ''"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chapter_state_requirements_project_status "
            "ON chapter_state_requirements(project_id, status)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chapter_state_requirements_source_issue "
            "ON chapter_state_requirements(source_issue_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chapter_state_requirements_superseded_by "
            "ON chapter_state_requirements(superseded_by_requirement_id)"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE chapter_state_requirements "
            "ADD CONSTRAINT fk_chapter_state_requirements_superseded_by "
            "FOREIGN KEY (superseded_by_requirement_id) "
            "REFERENCES chapter_state_requirements(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        op.execute(
            "DO $$ BEGIN "
            "ALTER TABLE chapter_state_requirements "
            "ADD CONSTRAINT fk_chapter_state_requirements_source_issue "
            "FOREIGN KEY (source_issue_id) REFERENCES continuity_issues(id); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        return

    existing = {
        col["name"]
        for col in sa.inspect(bind).get_columns("chapter_state_requirements")
    }
    if "status" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        )
    if "superseded_by_requirement_id" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column(
                "superseded_by_requirement_id",
                sa.String(length=64),
                sa.ForeignKey("chapter_state_requirements.id"),
                nullable=True,
            ),
        )
    if "source_issue_id" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column(
                "source_issue_id",
                sa.String(length=64),
                sa.ForeignKey("continuity_issues.id"),
                nullable=True,
            ),
        )
    if "status_reason" not in existing:
        op.add_column(
            "chapter_state_requirements",
            sa.Column("status_reason", sa.Text(), nullable=False, server_default=""),
        )
    op.create_index(
        "ix_chapter_state_requirements_project_status",
        "chapter_state_requirements",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_chapter_state_requirements_source_issue",
        "chapter_state_requirements",
        ["source_issue_id"],
        unique=False,
    )
    op.create_index(
        "ix_chapter_state_requirements_superseded_by",
        "chapter_state_requirements",
        ["superseded_by_requirement_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chapter_state_requirements_superseded_by",
        table_name="chapter_state_requirements",
    )
    op.drop_index(
        "ix_chapter_state_requirements_source_issue",
        table_name="chapter_state_requirements",
    )
    op.drop_index(
        "ix_chapter_state_requirements_project_status",
        table_name="chapter_state_requirements",
    )
    op.drop_column("chapter_state_requirements", "status_reason")
    op.drop_column("chapter_state_requirements", "source_issue_id")
    op.drop_column("chapter_state_requirements", "superseded_by_requirement_id")
    op.drop_column("chapter_state_requirements", "status")
