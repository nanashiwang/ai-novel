"""为 novel_specs 增加 (organization_id, project_id) 唯一约束

Revision ID: 0006_novel_specs_unique
Revises: 0005_plot_threads
Create Date: 2026-05-19 11:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006_novel_specs_unique"
down_revision: Union[str, None] = "0005_plot_threads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 防止 generate_bible 并发 race 时为同一 project 写入多条 NovelSpec，
    # 导致后续 get_by 抛 MultipleResultsFound。
    with op.batch_alter_table("novel_specs") as batch:
        batch.create_unique_constraint(
            "uq_novel_specs_org_project",
            ["organization_id", "project_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("novel_specs") as batch:
        batch.drop_constraint("uq_novel_specs_org_project", type_="unique")
