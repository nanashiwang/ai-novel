"""Per-scene POV anchor

Revision ID: 0020_scene_pov
Revises: 0016_memory_embedding_hnsw
Create Date: 2026-05-22 10:00:00

Sprint 14-C6：为 scenes 加 pov_character_name 字段。

- 用名字（VARCHAR(120) NULL）而不是 character_id：scenes.characters 本就是
  名字数组，保持一致；用 nullable 表示"该场景未单独锚定 POV，回落到
  spec.narrative_pov"。
- ContextBuilder 据此过滤 characters 段中非 POV 角色的隐私字段
  （secret / motivation / arc / current_state），避免"全知视角泄密"。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_scene_pov"
down_revision: str | None = "0016_memory_embedding_hnsw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS "
            "pov_character_name VARCHAR(120)"
        )
    else:
        op.add_column(
            "scenes",
            sa.Column("pov_character_name", sa.String(length=120), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE scenes DROP COLUMN IF EXISTS pov_character_name")
    else:
        op.drop_column("scenes", "pov_character_name")
