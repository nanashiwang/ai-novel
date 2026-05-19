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
    """
    CREATE TABLE IF NOT EXISTS draft_versions (
      id TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      chapter_id TEXT REFERENCES chapters(id),
      scene_id TEXT REFERENCES scenes(id),
      version_type TEXT NOT NULL DEFAULT 'draft',
      content TEXT NOT NULL DEFAULT '',
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
]


async def ensure_runtime_schema() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        return

    async with engine.begin() as conn:
        for statement in _POSTGRES_SCHEMA_FIXES:
            await conn.execute(text(statement))

    logger.info("runtime_schema_checked")
