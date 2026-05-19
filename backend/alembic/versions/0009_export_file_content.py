"""为 export_files 增加 content + file_size 字段

Revision ID: 0009_export_file_content
Revises: 0008_rename_scene_write_job_type
Create Date: 2026-05-19 22:00:00

Sprint 5-B：把导出内容直接存 db，免去 MinIO/S3 依赖；Sprint 6 真实部署
时把 content 迁出到对象存储，把 file_url 改为预签名 URL。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_export_file_content"
down_revision: Union[str, None] = "0008_rename_scene_write_job_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "export_files",
        sa.Column("content", sa.Text, nullable=False, server_default=""),
    )
    op.add_column(
        "export_files",
        sa.Column("file_size", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("export_files", "file_size")
    op.drop_column("export_files", "content")
