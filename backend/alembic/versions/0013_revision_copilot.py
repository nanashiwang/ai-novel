"""AI 设定共创提案表

Revision ID: 0013_revision_copilot
Revises: 0012_draft_versions_content_format
Create Date: 2026-05-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_revision_copilot"
down_revision: str | None = "0012_draft_versions_content_format"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revision_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="story_bible"),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="AI 设定共创"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_revision_sessions_project", "revision_sessions", ["project_id"])

    op.create_table(
        "revision_messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["revision_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_revision_messages_session", "revision_messages", ["session_id"])
    op.create_index("ix_revision_messages_project", "revision_messages", ["project_id"])

    op.create_table(
        "revision_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="update"),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="设定优化提案"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("impact", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("patch", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["revision_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_revision_proposals_session", "revision_proposals", ["session_id"])
    op.create_index("ix_revision_proposals_project", "revision_proposals", ["project_id"])
    op.create_index(
        "ix_revision_proposals_target",
        "revision_proposals",
        ["target_type", "target_id"],
    )

    op.create_table(
        "revision_applied_changes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("before_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("after_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("applied_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["revision_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["revision_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"]),
    )
    op.create_index(
        "ix_revision_applied_changes_proposal",
        "revision_applied_changes",
        ["proposal_id"],
    )
    op.create_index(
        "ix_revision_applied_changes_project",
        "revision_applied_changes",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_revision_applied_changes_project", table_name="revision_applied_changes")
    op.drop_index("ix_revision_applied_changes_proposal", table_name="revision_applied_changes")
    op.drop_table("revision_applied_changes")
    op.drop_index("ix_revision_proposals_target", table_name="revision_proposals")
    op.drop_index("ix_revision_proposals_project", table_name="revision_proposals")
    op.drop_index("ix_revision_proposals_session", table_name="revision_proposals")
    op.drop_table("revision_proposals")
    op.drop_index("ix_revision_messages_project", table_name="revision_messages")
    op.drop_index("ix_revision_messages_session", table_name="revision_messages")
    op.drop_table("revision_messages")
    op.drop_index("ix_revision_sessions_project", table_name="revision_sessions")
    op.drop_table("revision_sessions")
