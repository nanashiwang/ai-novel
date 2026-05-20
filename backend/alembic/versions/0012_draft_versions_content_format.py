"""draft_versions.content_format 列

Revision ID: 0012_draft_versions_content_format
Revises: 0011_database_indexes
Create Date: 2026-05-21

为 draft_versions 引入 content_format，标识 content 字段的序列化格式。
取值范围：
- "text"      —— 纯文本（历史数据默认）
- "markdown"  —— Markdown 字符串（新写入路径：AI 生成 / 用户手动编辑）

旧数据保持 "text"，由前端按纯文本渲染；新版本按 markdown 加载到 Tiptap。
content 列仍为 TEXT，不切换为 jsonb，避免 USING 转换与大规模回填。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_draft_versions_content_format"
down_revision: Union[str, None] = "0011_database_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "draft_versions",
        sa.Column(
            "content_format",
            sa.String(length=16),
            nullable=False,
            server_default="text",
        ),
    )


def downgrade() -> None:
    op.drop_column("draft_versions", "content_format")
