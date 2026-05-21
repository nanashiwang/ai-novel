"""风格样本（style_samples）

Revision ID: 0021_style_samples
Revises: 0020_scene_pov
Create Date: 2026-05-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_style_samples"
down_revision: str | None = "0020_scene_pov"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # PG 上 embedding 用 JSONB 存储（后续可平滑切到 pgvector，schema 兼容）；
    # 其它方言（SQLite 测试）用 JSON。
    if dialect == "postgresql":
        embedding_type = sa.dialects.postgresql.JSONB(astext_type=sa.Text())
    else:
        embedding_type = sa.JSON()

    op.create_table(
        "style_samples",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", embedding_type, nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_style_samples_organization_id",
        "style_samples",
        ["organization_id"],
    )
    op.create_index("ix_style_samples_project_id", "style_samples", ["project_id"])
    op.create_index(
        "ix_style_samples_project_created",
        "style_samples",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_style_samples_project_created", table_name="style_samples")
    op.drop_index("ix_style_samples_project_id", table_name="style_samples")
    op.drop_index("ix_style_samples_organization_id", table_name="style_samples")
    op.drop_table("style_samples")
