"""数据库索引优化（按优化方向文档 §3.7）

Revision ID: 0011_database_indexes
Revises: 0010_generation_jobs_dedupe_key
Create Date: 2026-05-19 23:50:00

为 Admin 列表 / 用户旅程的高频查询补复合索引。所有索引使用全表形式而非
partial，以保持 SQLite 测试环境与 PostgreSQL 生产环境的一致性；partial
index 的性能优势在中小规模下不显著，等表行数过 100 万再考虑。

未实施的索引：
- memory_entries HNSW on embedding — pgvector 扩展，留到 Sprint 7+ 真实
  向量召回时由专门迁移加。
- quota_balances unique constraint (org, key, period) — 模型层已有等价
  unique constraint（uq_novel_specs_org_project 模式可推广），暂不重复加
  以免与既有数据冲突。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0011_database_indexes"
down_revision: Union[str, None] = "0010_generation_jobs_dedupe_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # projects：Studio 项目列表（按租户）+ Admin 项目筛选（按状态/更新时间）
    op.create_index(
        "ix_projects_org_status_updated",
        "projects",
        ["organization_id", "status", "updated_at"],
    )

    # generation_jobs：
    # ① "本项目所有 jobs 按时间倒序"（Studio 任务页）
    # ② "本租户某状态 jobs 按时间倒序"（Admin 任务页 + status 过滤）
    op.create_index(
        "ix_jobs_org_project_created",
        "generation_jobs",
        ["organization_id", "project_id", "created_at"],
    )
    op.create_index(
        "ix_jobs_org_status_created",
        "generation_jobs",
        ["organization_id", "status", "created_at"],
    )

    # model_calls：Admin drill-down（按项目/任务过滤）
    op.create_index(
        "ix_model_calls_org_project_job",
        "model_calls",
        ["organization_id", "project_id", "job_id", "created_at"],
    )

    # usage_events：账单/用量页（按租户时间倒序）+ 项目级用量 drill-down
    op.create_index(
        "ix_usage_events_org_created",
        "usage_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_usage_events_project_type_created",
        "usage_events",
        ["project_id", "event_type", "created_at"],
    )

    # quota_reservations：定时任务扫描过期未结算的 reservation
    op.create_index(
        "ix_quota_reservations_org_status_expires",
        "quota_reservations",
        ["organization_id", "status", "expires_at"],
    )

    # admin_audit_logs：按 actor 或 organization 排查
    op.create_index(
        "ix_admin_audit_logs_org_created",
        "admin_audit_logs",
        ["organization_id", "created_at"],
    )

    # continuity_issues：按 scene 列出问题（写作页底部审稿面板��
    op.create_index(
        "ix_continuity_issues_scene_status",
        "continuity_issues",
        ["scene_id", "status"],
    )

    # draft_versions：scene 版本列表
    op.create_index(
        "ix_draft_versions_scene_created",
        "draft_versions",
        ["scene_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_draft_versions_scene_created", table_name="draft_versions")
    op.drop_index("ix_continuity_issues_scene_status", table_name="continuity_issues")
    op.drop_index("ix_admin_audit_logs_org_created", table_name="admin_audit_logs")
    op.drop_index("ix_quota_reservations_org_status_expires", table_name="quota_reservations")
    op.drop_index("ix_usage_events_project_type_created", table_name="usage_events")
    op.drop_index("ix_usage_events_org_created", table_name="usage_events")
    op.drop_index("ix_model_calls_org_project_job", table_name="model_calls")
    op.drop_index("ix_jobs_org_status_created", table_name="generation_jobs")
    op.drop_index("ix_jobs_org_project_created", table_name="generation_jobs")
    op.drop_index("ix_projects_org_status_updated", table_name="projects")
