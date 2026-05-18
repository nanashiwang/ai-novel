"""第二版迁移：补齐 Project 字段 + 关键外键 CASCADE 删除

Revision ID: 0002_project_fields_cascade
Revises: 0001_initial_schema
Create Date: 2026-05-16 04:50:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_project_fields_cascade"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 项目下属的子表 → 父表为 projects；删项目时一并清理
_CASCADE_TARGETS = [
    ("novel_specs", "project_id"),
    ("volumes", "project_id"),
    ("chapters", "project_id"),
    ("scenes", "project_id"),
    ("characters", "project_id"),
    ("world_items", "project_id"),
    ("memory_entries", "project_id"),
    ("generation_jobs", "project_id"),
    ("continuity_issues", "project_id"),
    ("draft_versions", "project_id"),
    ("export_files", "project_id"),
]


def upgrade() -> None:
    # 1) Project 字段补齐
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column("current_word_count", sa.Integer, nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("completed_chapter_count", sa.Integer, nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("cover_url", sa.String(500), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("tags", sa.JSON, nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column("target_reader", sa.String(500), nullable=False, server_default="")
        )

    # 2) 关键外键改为 ON DELETE CASCADE
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        # Postgres：先 drop 老约束再 add 带 ON DELETE CASCADE 的约束
        for table, column in _CASCADE_TARGETS:
            constraint_name = f"{table}_{column}_fkey"
            op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{constraint_name}"')
            op.create_foreign_key(
                f"{table}_{column}_fkey_cascade",
                table,
                "projects",
                [column],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("target_reader")
        batch.drop_column("tags")
        batch.drop_column("cover_url")
        batch.drop_column("completed_chapter_count")
        batch.drop_column("current_word_count")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table, column in _CASCADE_TARGETS:
            op.drop_constraint(
                f"{table}_{column}_fkey_cascade", table, type_="foreignkey"
            )
            op.create_foreign_key(
                f"{table}_{column}_fkey",
                table,
                "projects",
                [column],
                ["id"],
            )
