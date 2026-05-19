"""新增 plot_threads 表

Revision ID: 0005_plot_threads
Revises: 0004_system_settings
Create Date: 2026-05-19 10:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_plot_threads"
down_revision: Union[str, None] = "0004_system_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_threads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("thread_type", sa.String(64), nullable=False, server_default="main"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column(
            "related_characters",
            sa.JSON,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("opened_at_scene_id", sa.String(64), nullable=True),
        sa.Column("closed_at_scene_id", sa.String(64), nullable=True),
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
    )
    op.create_index(
        "ix_plot_threads_organization_id", "plot_threads", ["organization_id"]
    )
    op.create_index("ix_plot_threads_project_id", "plot_threads", ["project_id"])
    op.create_index("ix_plot_threads_status", "plot_threads", ["status"])


def downgrade() -> None:
    op.drop_index("ix_plot_threads_status", table_name="plot_threads")
    op.drop_index("ix_plot_threads_project_id", table_name="plot_threads")
    op.drop_index("ix_plot_threads_organization_id", table_name="plot_threads")
    op.drop_table("plot_threads")
