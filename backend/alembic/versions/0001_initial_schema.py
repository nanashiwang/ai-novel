"""初始化全部表结构

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-16 04:30:00

依据 app/models/ 下全部 ORM 模型生成的初始迁移。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_platform_staff", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("platform_role", sa.String(64), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("type", sa.String(32), nullable=False, server_default="personal"),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_code", sa.String(64), nullable=False, server_default="Free"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_plan_code", "organizations", ["plan_code"])

    # organization_members
    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default="member"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_members_org_user"),
    )
    op.create_index("ix_org_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_org_members_user_id", "organization_members", ["user_id"])

    # plans
    op.create_table(
        "plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("price_monthly", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("price_yearly", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "plan_features",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("plan_id", sa.String(64), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("feature_key", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("limit_value", sa.Integer),
        sa.Column("limit_unit", sa.String(32), nullable=False, server_default="times"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plan_features_plan_id", "plan_features", ["plan_id"])
    op.create_index("ix_plan_features_feature_key", "plan_features", ["feature_key"])

    # projects
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("genre", sa.String(120), nullable=False, server_default=""),
        sa.Column("target_word_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("target_chapter_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("language", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("style", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_index("ix_projects_title", "projects", ["title"])

    op.create_table(
        "novel_specs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("premise", sa.Text, nullable=False, server_default=""),
        sa.Column("theme", sa.String(500), nullable=False, server_default=""),
        sa.Column("genre", sa.String(120), nullable=False, server_default=""),
        sa.Column("tone", sa.String(500), nullable=False, server_default=""),
        sa.Column("target_reader", sa.String(500), nullable=False, server_default=""),
        sa.Column("narrative_pov", sa.String(200), nullable=False, server_default=""),
        sa.Column("style_guide", sa.Text, nullable=False, server_default=""),
        sa.Column("constraints", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_novel_specs_organization_id", "novel_specs", ["organization_id"])
    op.create_index("ix_novel_specs_project_id", "novel_specs", ["project_id"])

    # volumes & chapters
    op.create_table(
        "volumes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("volume_index", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("goal", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_volumes_organization_id", "volumes", ["organization_id"])
    op.create_index("ix_volumes_project_id", "volumes", ["project_id"])

    op.create_table(
        "chapters",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("volume_id", sa.String(64), sa.ForeignKey("volumes.id")),
        sa.Column("chapter_index", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("goal", sa.Text, nullable=False, server_default=""),
        sa.Column("conflict", sa.Text, nullable=False, server_default=""),
        sa.Column("ending_hook", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chapters_organization_id", "chapters", ["organization_id"])
    op.create_index("ix_chapters_project_id", "chapters", ["project_id"])

    op.create_table(
        "scenes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("scene_index", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("time_marker", sa.String(120), nullable=False, server_default=""),
        sa.Column("location", sa.String(200), nullable=False, server_default=""),
        sa.Column("characters", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("goal", sa.Text, nullable=False, server_default=""),
        sa.Column("conflict", sa.Text, nullable=False, server_default=""),
        sa.Column("emotion_start", sa.String(120), nullable=False, server_default=""),
        sa.Column("emotion_end", sa.String(120), nullable=False, server_default=""),
        sa.Column("reveal", sa.Text, nullable=False, server_default=""),
        sa.Column("hook", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scenes_organization_id", "scenes", ["organization_id"])
    op.create_index("ix_scenes_project_id", "scenes", ["project_id"])
    op.create_index("ix_scenes_chapter_id", "scenes", ["chapter_id"])

    # characters / world_items / memory
    op.create_table(
        "characters",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(120), nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("personality", sa.Text, nullable=False, server_default=""),
        sa.Column("motivation", sa.Text, nullable=False, server_default=""),
        sa.Column("secret", sa.Text, nullable=False, server_default=""),
        sa.Column("arc", sa.Text, nullable=False, server_default=""),
        sa.Column("relationships", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("current_state", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_characters_organization_id", "characters", ["organization_id"])
    op.create_index("ix_characters_project_id", "characters", ["project_id"])
    op.create_index("ix_characters_name", "characters", ["name"])

    op.create_table(
        "world_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("rules", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("related_characters", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("importance", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("is_hard_rule", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_world_items_organization_id", "world_items", ["organization_id"])
    op.create_index("ix_world_items_project_id", "world_items", ["project_id"])
    op.create_index("ix_world_items_type", "world_items", ["type"])

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="scene"),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("memory_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("importance", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memory_organization_id", "memory_entries", ["organization_id"])
    op.create_index("ix_memory_project_id", "memory_entries", ["project_id"])

    # generation_jobs / model_calls / usage_events
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("priority", sa.String(64), nullable=False, server_default="queue_standard"),
        sa.Column("plan_code", sa.String(64), nullable=False, server_default="Free"),
        sa.Column("reserved_quota", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consumed_quota", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("output_payload", sa.JSON),
        sa.Column("error_message", sa.Text),
        sa.Column("workflow_id", sa.String(200)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_organization_id", "generation_jobs", ["organization_id"])
    op.create_index("ix_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_index("ix_jobs_status", "generation_jobs", ["status"])
    op.create_index("ix_jobs_job_type", "generation_jobs", ["job_type"])
    op.create_index("ix_jobs_workflow_id", "generation_jobs", ["workflow_id"])

    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("generation_jobs.id")),
        sa.Column("task_type", sa.String(120), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_key", sa.String(160), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default="v1"),
        sa.Column("system_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("user_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("response_text", sa.Text),
        sa.Column("response_json", sa.JSON),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_calls_organization_id", "model_calls", ["organization_id"])
    op.create_index("ix_calls_task_type", "model_calls", ["task_type"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(64)),
        sa.Column("job_id", sa.String(64)),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("event_metadata", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_organization_id", "usage_events", ["organization_id"])
    op.create_index("ix_usage_user_id", "usage_events", ["user_id"])

    # quotas
    op.create_table(
        "quota_balances",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("quota_key", sa.String(120), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_value", sa.Integer, nullable=False),
        sa.Column("used_value", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reserved_value", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "quota_key", name="uq_quota_org_key"),
    )
    op.create_index("ix_quota_organization_id", "quota_balances", ["organization_id"])
    op.create_index("ix_quota_key", "quota_balances", ["quota_key"])

    op.create_table(
        "quota_reservations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("generation_jobs.id"), nullable=False),
        sa.Column("quota_key", sa.String(120), nullable=False),
        sa.Column("reserved_amount", sa.Integer, nullable=False),
        sa.Column("consumed_amount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="reserved"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reservation_organization_id", "quota_reservations", ["organization_id"])
    op.create_index("ix_reservation_job_id", "quota_reservations", ["job_id"])

    # continuity_issues / draft_versions / export_files / audit_logs
    op.create_table(
        "continuity_issues",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id")),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("scenes.id")),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("suggested_fix", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_issues_organization_id", "continuity_issues", ["organization_id"])
    op.create_index("ix_issues_project_id", "continuity_issues", ["project_id"])

    op.create_table(
        "draft_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id")),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("scenes.id")),
        sa.Column("version_type", sa.String(64), nullable=False, server_default="draft"),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("word_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(64), nullable=False, server_default="draft"),
        sa.Column("parent_version_id", sa.String(64)),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_drafts_organization_id", "draft_versions", ["organization_id"])
    op.create_index("ix_drafts_project_id", "draft_versions", ["project_id"])

    op.create_table(
        "export_files",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("export_type", sa.String(64), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exports_organization_id", "export_files", ["organization_id"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(160), nullable=False),
        sa.Column("target_type", sa.String(120), nullable=False),
        sa.Column("target_id", sa.String(120), nullable=False),
        sa.Column("before_data", sa.JSON),
        sa.Column("after_data", sa.JSON),
        sa.Column("ip_address", sa.String(80)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_organization_id", "admin_audit_logs", ["organization_id"])
    op.create_index("ix_audit_actor", "admin_audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_action", "admin_audit_logs", ["action"])


def downgrade() -> None:
    for table in [
        "admin_audit_logs",
        "export_files",
        "draft_versions",
        "continuity_issues",
        "quota_reservations",
        "quota_balances",
        "usage_events",
        "model_calls",
        "generation_jobs",
        "memory_entries",
        "world_items",
        "characters",
        "scenes",
        "chapters",
        "volumes",
        "novel_specs",
        "projects",
        "plan_features",
        "plans",
        "organization_members",
        "organizations",
        "users",
    ]:
        op.drop_table(table)
