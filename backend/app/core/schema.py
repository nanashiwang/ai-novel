"""轻量级运行时 schema 修复。

当前项目仍用 docker init SQL 做一键部署，已有数据卷不会重新执行 init SQL。
这里补齐早期数据卷缺失的字段/表，保证注册登录这类核心流程可用。
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger(__name__)


_POSTGRES_SCHEMA_FIXES = [
    """
    INSERT INTO plans (id, code, name, description, price_monthly, price_yearly, currency, status)
    VALUES
      ('plan_free', 'Free', 'Free', '免费体验：故事圣经与短篇生成', 0, NULL, 'CNY', 'active'),
      ('plan_starter', 'Starter', 'Starter', '适合轻量连载作者', 49, 490, 'CNY', 'active'),
      ('plan_pro', 'Pro', 'Pro', '长篇小说自动生产与审稿', 129, 1290, 'CNY', 'active'),
      ('plan_team', 'Team', 'Team', '多人协作、API Key 与高级审核', 399, 3990, 'CNY', 'active'),
      (
        'plan_enterprise',
        'Enterprise',
        'Enterprise',
        '专属队列、合同额度和审计导出',
        0,
        NULL,
        'CNY',
        'active'
      )
    ON CONFLICT (code) DO NOTHING
    """,
    """
    WITH seed(code, feature_key, limit_value, limit_unit) AS (
      VALUES
        ('Free', 'monthly_generated_words', 50000, 'words'),
        ('Free', 'monthly_review_count', 10, 'times'),
        ('Starter', 'monthly_generated_words', 300000, 'words'),
        ('Starter', 'monthly_review_count', 80, 'times'),
        ('Pro', 'monthly_generated_words', 1000000, 'words'),
        ('Pro', 'monthly_review_count', 300, 'times'),
        ('Pro', 'monthly_rewrite_count', 180, 'times'),
        ('Team', 'monthly_generated_words', 5000000, 'words'),
        ('Team', 'monthly_review_count', 1500, 'times'),
        ('Team', 'api_keys', 10, 'keys'),
        ('Enterprise', 'monthly_generated_words', 999999999, 'words'),
        ('Enterprise', 'dedicated_queue', 1, 'boolean')
    )
    INSERT INTO plan_features (
      id, plan_id, feature_key, enabled, limit_value, limit_unit, created_at, updated_at
    )
    SELECT
      'pf_' || lower(seed.code) || '_' || seed.feature_key,
      plans.id,
      seed.feature_key,
      true,
      seed.limit_value,
      seed.limit_unit,
      now(),
      now()
    FROM seed
    JOIN plans ON plans.code = seed.code
    WHERE NOT EXISTS (
      SELECT 1
      FROM plan_features existing
      WHERE existing.plan_id = plans.id
        AND existing.feature_key = seed.feature_key
    )
    """,
    "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS plan_code TEXT NOT NULL DEFAULT 'Free'",
    "CREATE INDEX IF NOT EXISTS ix_organizations_plan_code ON organizations(plan_code)",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS current_word_count INTEGER NOT NULL DEFAULT 0",
    (
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS "
        "completed_chapter_count INTEGER NOT NULL DEFAULT 0"
    ),
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS cover_url TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS target_reader TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10, 4) NOT NULL DEFAULT 0",
    (
        "ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ),
    (
        "ALTER TABLE novel_specs ADD COLUMN IF NOT EXISTS "
        "continuity_rules JSONB NOT NULL DEFAULT '[]'"
    ),
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS scene_purpose TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS entry_state TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS exit_state TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS must_include JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS must_avoid JSONB NOT NULL DEFAULT '[]'",
    # Sprint 14-C6：Per-scene POV 锚定
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS pov_character_name VARCHAR(120)",
    "ALTER TABLE export_files ADD COLUMN IF NOT EXISTS content TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE export_files ADD COLUMN IF NOT EXISTS file_size INTEGER NOT NULL DEFAULT 0",
    (
        "ALTER TABLE export_files ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ),
    # draft_versions：富文本格式标识（Sprint 4-C：升级编辑器为 markdown）
    (
        "ALTER TABLE draft_versions ADD COLUMN IF NOT EXISTS "
        "content_format VARCHAR(16) NOT NULL DEFAULT 'text'"
    ),
    "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS event_metadata JSONB",
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'usage_events'
          AND column_name = 'metadata'
      ) THEN
        EXECUTE 'UPDATE usage_events SET event_metadata = metadata WHERE event_metadata IS NULL';
      END IF;
    END $$;
    """,
    (
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ),
    (
        "ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ),
    "ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS dedupe_key TEXT",
    (
        "CREATE INDEX IF NOT EXISTS ix_generation_jobs_dedupe "
        "ON generation_jobs(organization_id, dedupe_key, status)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_jobs_org_project_created "
        "ON generation_jobs(organization_id, project_id, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_jobs_org_status_created "
        "ON generation_jobs(organization_id, status, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_memory_project_type_created "
        "ON memory_entries(project_id, memory_type, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_memory_project_source_created "
        "ON memory_entries(project_id, source_type, source_id, created_at)"
    ),
    """
    CREATE TABLE IF NOT EXISTS revision_sessions (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      created_by TEXT NOT NULL REFERENCES users(id),
      scope TEXT NOT NULL DEFAULT 'story_bible',
      title TEXT NOT NULL DEFAULT 'AI 设定共创',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_revision_sessions_project ON revision_sessions(project_id)",
    """
    CREATE TABLE IF NOT EXISTS revision_messages (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      session_id TEXT NOT NULL REFERENCES revision_sessions(id) ON DELETE CASCADE,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      role TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_revision_messages_session ON revision_messages(session_id)",
    "CREATE INDEX IF NOT EXISTS ix_revision_messages_project ON revision_messages(project_id)",
    """
    CREATE TABLE IF NOT EXISTS revision_proposals (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      session_id TEXT NOT NULL REFERENCES revision_sessions(id) ON DELETE CASCADE,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      target_type TEXT NOT NULL,
      target_id TEXT,
      action TEXT NOT NULL DEFAULT 'update',
      title TEXT NOT NULL DEFAULT '设定优化提案',
      reason TEXT NOT NULL DEFAULT '',
      impact JSONB NOT NULL DEFAULT '[]',
      patch JSONB NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_revision_proposals_session ON revision_proposals(session_id)",
    "CREATE INDEX IF NOT EXISTS ix_revision_proposals_project ON revision_proposals(project_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_revision_proposals_target "
        "ON revision_proposals(target_type, target_id)"
    ),
    """
    CREATE TABLE IF NOT EXISTS revision_applied_changes (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      session_id TEXT NOT NULL REFERENCES revision_sessions(id) ON DELETE CASCADE,
      proposal_id TEXT NOT NULL REFERENCES revision_proposals(id) ON DELETE CASCADE,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      target_type TEXT NOT NULL,
      target_id TEXT,
      before_data JSONB NOT NULL DEFAULT '{}',
      after_data JSONB NOT NULL DEFAULT '{}',
      applied_by TEXT NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_revision_applied_changes_proposal "
        "ON revision_applied_changes(proposal_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_revision_applied_changes_project "
        "ON revision_applied_changes(project_id)"
    ),
    # character_revisions：人物字段版本链（Sprint 10：动态人物画像系统）
    """
    CREATE TABLE IF NOT EXISTS character_revisions (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
      field VARCHAR(64) NOT NULL,
      old_value JSONB,
      new_value JSONB,
      reason TEXT NOT NULL DEFAULT '',
      source VARCHAR(16) NOT NULL,
      scene_id TEXT REFERENCES scenes(id),
      status VARCHAR(16) NOT NULL DEFAULT 'pending',
      created_by TEXT NOT NULL REFERENCES users(id),
      applied_by TEXT REFERENCES users(id),
      applied_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_character_revisions_char_status "
        "ON character_revisions(character_id, status, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_character_revisions_project_status "
        "ON character_revisions(project_id, status)"
    ),
    """
    CREATE TABLE IF NOT EXISTS draft_versions (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      chapter_id TEXT REFERENCES chapters(id),
      scene_id TEXT REFERENCES scenes(id),
      version_type TEXT NOT NULL DEFAULT 'draft',
      content TEXT NOT NULL DEFAULT '',
      content_format VARCHAR(16) NOT NULL DEFAULT 'text',
      word_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'draft',
      parent_version_id TEXT,
      created_by TEXT NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_draft_versions_org ON draft_versions(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_draft_versions_project ON draft_versions(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_draft_versions_scene ON draft_versions(scene_id)",
    """
    CREATE TABLE IF NOT EXISTS organization_invitations (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      email TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'editor',
      token TEXT UNIQUE NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      invited_by TEXT NOT NULL REFERENCES users(id),
      expires_at TIMESTAMPTZ NOT NULL,
      accepted_by TEXT REFERENCES users(id),
      accepted_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_invitations_organization_id "
        "ON organization_invitations(organization_id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_invitations_email ON organization_invitations(email)",
    "CREATE INDEX IF NOT EXISTS ix_invitations_status ON organization_invitations(status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_invitations_token ON organization_invitations(token)",
    """
    CREATE TABLE IF NOT EXISTS system_settings (
      key TEXT PRIMARY KEY,
      value TEXT,
      is_secret BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "DELETE FROM system_settings WHERE key = 'model_gateway.mode'",
    "ALTER TABLE IF EXISTS subscriptions ALTER COLUMN provider SET DEFAULT 'manual'",
    "ALTER TABLE IF EXISTS payment_events ALTER COLUMN provider SET DEFAULT 'manual'",
    """
    DO $$
    BEGIN
      IF to_regclass('public.subscriptions') IS NOT NULL THEN
        UPDATE subscriptions SET provider = 'manual' WHERE provider = 'mock';
      END IF;
      IF to_regclass('public.payment_events') IS NOT NULL THEN
        UPDATE payment_events SET provider = 'manual' WHERE provider = 'mock';
      END IF;
    END $$;
    """,
    # Sprint 12-C: 世界观条目 + 剧情线 revision 链
    """
    CREATE TABLE IF NOT EXISTS world_item_revisions (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      item_id TEXT NOT NULL REFERENCES world_items(id) ON DELETE CASCADE,
      field TEXT NOT NULL,
      old_value JSONB,
      new_value JSONB,
      reason TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'user_edit',
      scene_id TEXT,
      status TEXT NOT NULL DEFAULT 'applied',
      created_by TEXT,
      applied_by TEXT,
      applied_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_world_item_revisions_item_status "
        "ON world_item_revisions(item_id, status, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_world_item_revisions_project_status "
        "ON world_item_revisions(project_id, status)"
    ),
    """
    CREATE TABLE IF NOT EXISTS plot_thread_revisions (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      item_id TEXT NOT NULL REFERENCES plot_threads(id) ON DELETE CASCADE,
      field TEXT NOT NULL,
      old_value JSONB,
      new_value JSONB,
      reason TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'user_edit',
      scene_id TEXT,
      status TEXT NOT NULL DEFAULT 'applied',
      created_by TEXT,
      applied_by TEXT,
      applied_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_plot_thread_revisions_item_status "
        "ON plot_thread_revisions(item_id, status, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_plot_thread_revisions_project_status "
        "ON plot_thread_revisions(project_id, status)"
    ),
    # Sprint 13-B1：memory_entries 嵌入向量列 + HNSW（迁移 0016 等价补丁）
    "CREATE EXTENSION IF NOT EXISTS vector",
    "ALTER TABLE memory_entries ADD COLUMN IF NOT EXISTS embedding vector(1536)",
    (
        "CREATE INDEX IF NOT EXISTS ix_memory_embedding_hnsw "
        "ON memory_entries USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64) "
        "WHERE embedding IS NOT NULL"
    ),
    # Sprint 14-C5：信息释放 ledger
    """
    CREATE TABLE IF NOT EXISTS information_ledger (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      fact TEXT NOT NULL,
      owners JSONB NOT NULL DEFAULT '[]',
      disclosed_to JSONB NOT NULL DEFAULT '[]',
      first_revealed_scene_id VARCHAR(64),
      planned_reveal_chapter INTEGER,
      status VARCHAR(16) NOT NULL DEFAULT 'secret',
      importance INTEGER NOT NULL DEFAULT 3,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_information_ledger_organization_id "
        "ON information_ledger(organization_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_information_ledger_project_id "
        "ON information_ledger(project_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_information_ledger_status "
        "ON information_ledger(status)"
    ),
]


async def ensure_runtime_schema() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        return

    async with engine.begin() as conn:
        for statement in _POSTGRES_SCHEMA_FIXES:
            await conn.execute(text(statement))

    logger.info("runtime_schema_checked")
