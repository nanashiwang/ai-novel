"""契约枚举值的代码侧真相源。

本模块与 docs/api_contract_v1.md 一一对应，作为契约 lint 测试
（tests/test_contract_consistency.py）的对照参考。任何向集合内
新增枚举值都必须同步更新契约文档；任何在代码中出现但**不在**集合
内的契约字面量，会被 lint 测试视为违规。

注意：本模块不强制 service / workflow 代码必须导入这些常量
（保留 hardcoded 字面量是 OK 的，YAGNI 原则下不为了引用而引用）。
其唯一职责是固化"什么值是合法的"，让漂移在 CI 中被自动捕获。
"""
from __future__ import annotations

# ----------------------------------------------------------------------------
# generation_jobs.job_type — docs/api_contract_v1.md §4.1
# ----------------------------------------------------------------------------
# 当前已在代码中产生（Sprint 1 完成）：
#   generate_bible / write_scene / full_novel
# 后续 Sprint 占位（路由/契约已登记，实现待 Sprint X）：
#   generate_outline (S2), generate_scene_plan (S3),
#   audit_scene (S5), rewrite_scene (S5), export_novel (S5)
JOB_TYPES: frozenset[str] = frozenset(
    {
        "generate_bible",
        "generate_outline",
        "generate_scene_plan",
        "write_scene",
        "full_novel",
        "audit_scene",
        "rewrite_scene",
        "export_novel",
    }
)


# ----------------------------------------------------------------------------
# generation_jobs.status — docs/api_contract_v1.md §4.2
# ----------------------------------------------------------------------------
# v1 简化状态机。失败的细分原因走 error_code 字段，不挤进 status。
# 优化方向文档建议的细分（quota_insufficient/permission_denied 等）
# 推到 v2 评估。
JOB_STATUSES: frozenset[str] = frozenset(
    {
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }
)


# ----------------------------------------------------------------------------
# projects.status — docs/api_contract_v1.md §4.3
# ----------------------------------------------------------------------------
# 当前已在代码中流转：
#   created / bible_generating / bible_ready / outlined /
#   scenes_planned / drafting
# 后续 Sprint 占位：
#   outline_generating (S2), scenes_planning (S3), completed (S4+)
PROJECT_STATUSES: frozenset[str] = frozenset(
    {
        "created",
        "bible_generating",
        "bible_ready",
        "outline_generating",
        "outlined",
        "scenes_planning",
        "scenes_planned",
        "drafting",
        "completed",
    }
)


# ----------------------------------------------------------------------------
# error code — docs/api_contract_v1.md §4.4
# ----------------------------------------------------------------------------
# 新增 error code 时必须先登记本表 + 契约文档；命名 snake_case，资源不存在
# 用 <resource>_not_found 约定。
ERROR_CODES: frozenset[str] = frozenset(
    {
        # 通用
        "not_found",
        "permission_denied",
        "validation_error",
        "internal_error",
        "http_error",
        "app_error",
        "conflict",
        # 资源不存在
        "project_not_found",
        "novel_spec_not_found",
        "job_not_found",
        "scene_not_found",
        "chapter_not_found",
        "volume_not_found",
        "character_not_found",
        "world_item_not_found",
        "version_not_found",
        "export_not_found",
        "organization_not_found",
        "member_not_found",
        "quota_not_found",
        "draft_not_found",
        "revision_session_not_found",
        "revision_proposal_not_found",
        "character_revision_not_found",
        "plot_thread_not_found",
        "information_ledger_not_found",
        "style_sample_not_found",
        "prompt_experiment_not_found",
        "prompt_experiment_must_be_ended_before_delete",
        "chapter_revision_only_update",
        # 额度
        "quota_insufficient",
        "quota_not_in_plan",
        "invalid_amount",
        "amount_must_be_positive",
        # 参数
        "scene_id_required",
        "chapter_id_required",
        "export_type_not_supported",
        "job_not_retryable",
        "unknown_job_type",
        "revision_proposal_already_applied",
        "revision_action_not_supported",
        "revision_target_not_supported",
        "world_item_revision_not_found",
        "plot_thread_revision_not_found",
        # 套餐 / 组织管理
        "plan_not_found",
        "plan_inactive",
        "plan_in_use",
        "duplicate_feature_key",
        # 用户管理
        "user_not_found",
        "email_already_registered",
        "cannot_modify_self",
        "invalid_role",
    }
)


# ----------------------------------------------------------------------------
# generation limits
# ----------------------------------------------------------------------------
# 项目级章节大纲目标上限。超长篇允许设置较大目标，但实际生成会按批推进，
# 避免一次请求让模型输出数百章 JSON。
MAX_OUTLINE_CHAPTERS = 2000
OUTLINE_CHAPTER_BATCH_SIZE = 30


__all__ = [
    "JOB_TYPES",
    "JOB_STATUSES",
    "PROJECT_STATUSES",
    "ERROR_CODES",
    "MAX_OUTLINE_CHAPTERS",
    "OUTLINE_CHAPTER_BATCH_SIZE",
]
