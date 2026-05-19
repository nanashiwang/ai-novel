"""为 novel_specs 增加 continuity_rules JSON 字段

Revision ID: 0007_novel_specs_continuity_rules
Revises: 0006_novel_specs_unique
Create Date: 2026-05-19 12:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_novel_specs_continuity_rules"
down_revision: Union[str, None] = "0006_novel_specs_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 之前 generate_bible 把 bible.continuity_rules 折叠成 constraints 字符串，
    # ContextBuilder 后续无法精确还原。新增独立 JSON 列保留结构化数据。
    op.add_column(
        "novel_specs",
        sa.Column(
            "continuity_rules",
            sa.JSON,
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("novel_specs", "continuity_rules")
