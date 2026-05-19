"""为 generation_jobs 增加 dedupe_key 字段

Revision ID: 0010_generation_jobs_dedupe_key
Revises: 0009_export_file_content
Create Date: 2026-05-19 23:30:00

防止用户短时间内重复点"生成"按钮导致同一业务请求扣两份额度。
service 层在创建前查询 (organization_id, dedupe_key, status in queued/running)，
存在活跃 job 则直接返回。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_generation_jobs_dedupe_key"
down_revision: Union[str, None] = "0009_export_file_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("dedupe_key", sa.String(64), nullable=True),
    )
    # 复合索引：(organization_id, dedupe_key, status) 覆盖典型查询
    # "本租户下同 key 是否有活跃任务"
    op.create_index(
        "ix_generation_jobs_dedupe",
        "generation_jobs",
        ["organization_id", "dedupe_key", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_dedupe", table_name="generation_jobs")
    op.drop_column("generation_jobs", "dedupe_key")
