"""plot_threads: expected_resolve_chapter (Sprint 17-A防漂移).

Revision ID: 0025_plot_thread_eta
Revises: 0024_chapter_budget
Create Date: 2026-05-28

加 expected_resolve_chapter（Integer NULL）：开线时 LLM/用户估计预期收线
章节；ContextBuilder._fmt_plot_threads 读时计算 stalled（当前章 >
expected_resolve_chapter 且仍 open）。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_plot_thread_eta"
down_revision: str | None = "0024_chapter_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plot_threads",
        sa.Column("expected_resolve_chapter", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plot_threads", "expected_resolve_chapter")
