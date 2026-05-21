"""新增 information_ledger 表（Sprint 14-C5）。

Revision ID: 0019_information_ledger
Revises: 0018_model_calls_metadata
Create Date: 2026-05-22 10:00:00

把"主角真实身份 / 凶手是谁 / 神器真名"等需要分阶段释放的事实登记到
information_ledger，配合 LedgerService 校验"信息泄露"。详细字段语义见
``app/models/information_ledger.py`` 的 module docstring。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_information_ledger"
down_revision: str | None = "0018_model_calls_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "information_ledger",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact", sa.Text, nullable=False),
        sa.Column("owners", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("disclosed_to", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("first_revealed_scene_id", sa.String(64), nullable=True),
        sa.Column("planned_reveal_chapter", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="secret"),
        sa.Column("importance", sa.Integer, nullable=False, server_default="3"),
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
        "ix_information_ledger_organization_id",
        "information_ledger",
        ["organization_id"],
    )
    op.create_index(
        "ix_information_ledger_project_id",
        "information_ledger",
        ["project_id"],
    )
    op.create_index(
        "ix_information_ledger_status",
        "information_ledger",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_information_ledger_status", table_name="information_ledger")
    op.drop_index("ix_information_ledger_project_id", table_name="information_ledger")
    op.drop_index(
        "ix_information_ledger_organization_id", table_name="information_ledger"
    )
    op.drop_table("information_ledger")
