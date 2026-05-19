"""重命名 generation_jobs.job_type 'scene_write' → 'write_scene'

Revision ID: 0008_rename_scene_write_job_type
Revises: 0007_novel_specs_continuity_rules
Create Date: 2026-05-19 14:00:00

契约对齐：docs/api_contract_v1.md §4.1 把 job_type 命名约定统一为
"动作_对象"，旧值 "scene_write" 与其他三个值（generate_bible、
generate_outline、generate_scene_plan）不一致；本迁移把所有已有行
就地改名为 "write_scene"，代码层一并切换。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0008_rename_scene_write_job_type"
down_revision: Union[str, None] = "0007_novel_specs_continuity_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        text(
            "UPDATE generation_jobs SET job_type = 'write_scene' "
            "WHERE job_type = 'scene_write'"
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "UPDATE generation_jobs SET job_type = 'scene_write' "
            "WHERE job_type = 'write_scene'"
        )
    )
