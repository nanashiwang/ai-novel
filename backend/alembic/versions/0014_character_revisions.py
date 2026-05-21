"""character_revisions：人物字段版本链

Revision ID: 0014_character_revisions
Revises: 0013_revision_copilot
Create Date: 2026-05-21

为人物字段（name/role/description/personality/motivation/secret/arc/
current_state/relationships）的所有修改建立统一版本链：
- source='user_edit'   手动编辑（CharacterEditDialog）
- source='copilot'     AI 设定共创对话产生的提案
- source='ai_inferred' write_scene 后自动推演（Phase B 引入）

ContextBuilder 永远只读 status='applied' 的最新 revision 作为权威字段值。
任何修改前先建 revision，apply 时落到 characters 表，便于回滚。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_character_revisions"
down_revision: str | None = "0013_revision_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "character_revisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("applied_by", sa.String(length=64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"]),
    )
    op.create_index(
        "ix_character_revisions_char_status",
        "character_revisions",
        ["character_id", "status", "created_at"],
    )
    op.create_index(
        "ix_character_revisions_project_status",
        "character_revisions",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_character_revisions_project_status", table_name="character_revisions")
    op.drop_index("ix_character_revisions_char_status", table_name="character_revisions")
    op.drop_table("character_revisions")
