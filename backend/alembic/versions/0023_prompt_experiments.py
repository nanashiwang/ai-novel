"""Prompt experiments table (Sprint 15-D1).

Revision ID: 0023_prompt_experiments
Revises: 0022_revision_proposal_groups
Create Date: 2026-05-22

为 Prompt A/B 实验登记表。PG 加联合索引 (organization_id, prompt_key, status)
让 PromptRouter 的活跃实验查询尽量便宜。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_prompt_experiments"
down_revision: str | None = "0022_revision_proposal_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_experiments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("prompt_key", sa.String(160), nullable=False),
        sa.Column("variant_a_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("variant_b_version", sa.String(32), nullable=False, server_default="v2"),
        sa.Column("traffic_split_pct", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_prompt_experiments_active",
        "prompt_experiments",
        ["organization_id", "prompt_key", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_experiments_active", table_name="prompt_experiments")
    op.drop_table("prompt_experiments")
