"""新增 organization_invitations 表

Revision ID: 0003_organization_invitations
Revises: 0002_project_fields_cascade
Create Date: 2026-05-16 05:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_organization_invitations"
down_revision: Union[str, None] = "0002_project_fields_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default="editor"),
        sa.Column("token", sa.String(96), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("invited_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by", sa.String(64), sa.ForeignKey("users.id")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invitations_organization_id", "organization_invitations", ["organization_id"])
    op.create_index("ix_invitations_email", "organization_invitations", ["email"])
    op.create_index("ix_invitations_status", "organization_invitations", ["status"])
    op.create_index("ix_invitations_token", "organization_invitations", ["token"], unique=True)


def downgrade() -> None:
    op.drop_table("organization_invitations")
