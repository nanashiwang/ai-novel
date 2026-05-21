"""世界观条目 + 剧情线 revision 链。

Sprint 12-C：参考 character_revisions 的版本链 + AI 推演模式，给 world_items
与 plot_threads 也加 revision 表。让世界观条目（地点 / 势力 / 硬规则）和剧情线
（主线 / 副线 / 伏笔）能跟随情节自然演进：

- 用户手动编辑 → 写一条 applied revision，保留改动来源；
- AI 在 write_scene 后从正文反推字段变化 → 写 pending revision，需用户审核；
- copilot 共创提案 → pending revision，apply 后 supersede 旧 applied。

Revision ID: 0014_world_plot_revisions
Revises: 0013_revision_copilot
Create Date: 2026-05-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_world_plot_revisions"
down_revision: str | None = "0014_character_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_revision_table(name: str, fk_table: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="user_edit"),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="applied"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("applied_by", sa.String(length=64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint([f"item_id"], [f"{fk_table}.id"], ondelete="CASCADE"),
    )
    op.create_index(f"ix_{name}_item_status", name, ["item_id", "status", "created_at"])
    op.create_index(f"ix_{name}_project_status", name, ["project_id", "status"])


def upgrade() -> None:
    _create_revision_table("world_item_revisions", "world_items")
    _create_revision_table("plot_thread_revisions", "plot_threads")


def downgrade() -> None:
    op.drop_index("ix_plot_thread_revisions_project_status", table_name="plot_thread_revisions")
    op.drop_index("ix_plot_thread_revisions_item_status", table_name="plot_thread_revisions")
    op.drop_table("plot_thread_revisions")
    op.drop_index("ix_world_item_revisions_project_status", table_name="world_item_revisions")
    op.drop_index("ix_world_item_revisions_item_status", table_name="world_item_revisions")
    op.drop_table("world_item_revisions")
