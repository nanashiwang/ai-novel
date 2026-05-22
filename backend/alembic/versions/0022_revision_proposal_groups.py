"""revision proposal groups and chapter target

Revision ID: 0022_revision_proposal_groups
Revises: 0021_style_samples
Create Date: 2026-05-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_revision_proposal_groups"
down_revision: str | None = "0021_style_samples"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    op.add_column("revision_proposals", sa.Column("group_id", sa.String(length=64), nullable=True))
    op.add_column(
        "revision_proposals",
        sa.Column("group_title", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "revision_proposals",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "revision_proposals",
        sa.Column("risk_notes", _json_type(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_revision_proposals_group_id", "revision_proposals", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_revision_proposals_group_id", table_name="revision_proposals")
    op.drop_column("revision_proposals", "risk_notes")
    op.drop_column("revision_proposals", "is_primary")
    op.drop_column("revision_proposals", "group_title")
    op.drop_column("revision_proposals", "group_id")
