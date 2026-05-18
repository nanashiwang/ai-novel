"""新增 system_settings 表

Revision ID: 0004_system_settings
Revises: 0003_organization_invitations
Create Date: 2026-05-18 22:20:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_system_settings"
down_revision: Union[str, None] = "0003_organization_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("value", sa.Text),
        sa.Column("is_secret", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_settings")

